"""Respuestas reales de ambas APIs grabadas para probar la captura sin red, y las reglas que todo dato capturado cumple.

Uso:
  python3 scripts/capture_fixtures.py             # graba de nuevo las respuestas reales y el resultado esperado
  python3 scripts/capture_fixtures.py --expected  # solo regenera el esperado desde lo ya grabado (tras un cambio a propósito)

Graba en `tests/fixtures/capture/` un alcance chico pero variado de cada cadena (`SCOPES`): Cinemex el estado 18 de su
API (3 cines, Platinum, 3D, experiencias) y Cinépolis la ciudad `hermosillo` (4 cines, VIP, 4DX/Sala Junior, UTC−7 sin
horario de verano). Por cadena quedan dos archivos:
  - `{chain}.responses.json.gz`: cada petición (método, URL, cuerpo) con su respuesta tal cual, sin encabezados (ahí
    van las claves), y la hora de la grabación, que la reproducción congela para pedir los mismos días;
  - `{chain}.expected.json.gz`: lo que la captura produjo con ese crudo: filas normalizadas, cines y unidades.

`tests/test_capture_replay.py` corre la captura real (`cinemex.snapshot`, `cinepolis.snapshot`, `normalize`, `store`)
contra lo grabado y exige el mismo resultado. Si un cambio altera el dato a propósito, se revisa la diferencia y se
regenera el esperado con `--expected`; si no era a propósito, la prueba lo atrapó. `tests/test_live_capture.py` aplica
`problems()` a una captura en vivo del mismo alcance (`make test-live`). Solo librería estándar.
"""
import argparse
import gzip
import json
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import cinemex, cinepolis, normalize  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "capture"
SCOPES = {
    "cinemex": {"state_ids": [18]},
    "cinepolis": {"city_ids": ["hermosillo"]},
}
_MODULES = {"cinemex": cinemex, "cinepolis": cinepolis}

# Columnas que la captura llena siempre en ambas cadenas (comprobado sobre toda la cartelera vigente el 2026-09-25).
# Las que pueden venir vacías de la API: `genre`, `duration_min`, `distributor`, `experience` y `state_id` en Cinépolis.
REQUIRED = ("chain", "show_id", "cinema_id", "cinema_name", "lat", "lng", "city_id", "state_code", "movie_id",
            "movie_title", "title_norm", "rating", "date", "datetime_local", "datetime_utc", "screen", "language",
            "language_raw", "format", "premium_tier", "version_raw")
REQUIRED_BY_CHAIN = {"cinemex": ("state_id",), "cinepolis": ()}
# Los campos de tiempo de una unidad cambian en cada corrida; no son parte del dato.
_UNIT_VOLATILE = ("duration_s",)


def _key(method, url, body):
    return json.dumps([method, url, body], sort_keys=True, ensure_ascii=False)


@contextmanager
def recording(chain):
    """Deja pasar las peticiones de `chain` a la API y las anota; entrega la lista de llamadas."""
    module, calls, lock = _MODULES[chain], [], threading.Lock()
    real = module.request_json

    def record(url, *, method="GET", headers=None, body=None, retries=None):
        response = real(url, method=method, headers=headers, body=body, retries=retries)
        # Copia: la captura adelgaza lo que recibe (`_slim`) y se grabaría el payload ya recortado, no el de la API.
        with lock:
            calls.append({"method": method, "url": url, "body": body, "response": json.loads(json.dumps(response))})
        return response

    module.request_json = record
    try:
        yield calls
    finally:
        module.request_json = real


def _frozen_datetime(at):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    return Frozen


@contextmanager
def replaying(chain, recorded):
    """Responde las peticiones de `chain` con lo grabado y congela el reloj en la hora de la grabación. Una petición que
    no se grabó levanta `LookupError`: la captura pide algo distinto de lo que pedía."""
    module = _MODULES[chain]
    answers = {_key(c["method"], c["url"], c["body"]): c["response"] for c in recorded["calls"]}
    real_request, real_datetime = module.request_json, module.datetime

    def replay(url, *, method="GET", headers=None, body=None, retries=None):
        try:
            # Copia: la captura modifica lo que recibe (`_slim`, `setdefault`) y una respuesta puede pedirse dos veces.
            return json.loads(json.dumps(answers[_key(method, url, body)]))
        except KeyError:
            raise LookupError(f"petición no grabada: {method} {url} {json.dumps(body, ensure_ascii=False)[:300]}")

    module.request_json = replay
    module.datetime = _frozen_datetime(datetime.fromisoformat(recorded["recorded_at"]))
    try:
        yield
    finally:
        module.request_json, module.datetime = real_request, real_datetime


def capture(chain):
    """La captura de `chain` en el alcance de `SCOPES`, con el código de hoy: el crudo de `snapshot()`."""
    return _MODULES[chain].snapshot(**SCOPES[chain])


def result(chain, raw):
    """Lo que la captura extrae de un crudo: {rows, cinemas, units}, ordenado para comparar."""
    units = [{k: v for k, v in u.items() if k not in _UNIT_VOLATILE} for u in raw.get("units") or []]
    return {"rows": sorted(normalize.rows(chain, raw), key=lambda r: r["show_id"]),
            "cinemas": normalize.cinemas(chain, raw),
            "units": sorted(units, key=lambda u: u["unit"])}


def problems(chain, got):
    """Lo que un resultado de `result()` incumple de las reglas de todo dato capturado. Lista vacía = sano."""
    out = []
    rows, cinemas = got["rows"], {c["cinema_id"]: c for c in got["cinemas"]}
    if not rows:
        out.append("sin funciones")
    failed = [u for u in got["units"] if not u.get("ok")]
    out += [f"unidad {u['unit']} falló: {u.get('error')}" for u in failed]
    required = REQUIRED + REQUIRED_BY_CHAIN[chain]
    missing = {}
    for r in rows:
        if set(r) != set(normalize.COLUMNS):
            out.append(f"{r.get('show_id')}: columnas {sorted(set(r) ^ set(normalize.COLUMNS))} de más o de menos")
        for col in required:
            if r.get(col) in (None, ""):
                missing.setdefault(col, r["show_id"])
        if r.get("datetime_local") and r.get("date") != r["datetime_local"][:10]:
            out.append(f"{r['show_id']}: date {r['date']} no es el día de {r['datetime_local']}")
        if r.get("datetime_utc") and not r["datetime_utc"].endswith("+00:00"):
            out.append(f"{r['show_id']}: datetime_utc sin UTC: {r['datetime_utc']}")
        if r.get("cinema_id") not in cinemas:
            out.append(f"{r['show_id']}: el cine {r.get('cinema_id')} no está en la dimensión de cines")
    out += [f"{col} vacío (p. ej. {sid})" for col, sid in sorted(missing.items())]
    out += [f"cine {cid} sin state_code" for cid, c in sorted(cinemas.items()) if not c.get("state_code")]
    return out


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0: el mismo contenido da el mismo archivo, y git no ve cambios donde no los hay.
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=0).encode("utf-8"))


def load(chain, kind):
    """Lo grabado de `chain`: `kind` es `"responses"` o `"expected"`."""
    with gzip.open(FIXTURE_DIR / f"{chain}.{kind}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def replay(chain, recorded=None):
    """La captura de `chain` contra lo grabado: el crudo que produce hoy el código con esas respuestas."""
    recorded = recorded or load(chain, "responses")
    with replaying(chain, recorded):
        return capture(chain)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expected", action="store_true", help="solo regenera el esperado desde lo ya grabado")
    ap.add_argument("--chain", choices=sorted(SCOPES), help="solo una cadena")
    args = ap.parse_args(argv)
    bad = False
    for chain in [args.chain] if args.chain else sorted(SCOPES):
        if not args.expected:
            recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with recording(chain) as calls:
                capture(chain)
            calls.sort(key=lambda c: _key(c["method"], c["url"], c["body"]))
            _write(FIXTURE_DIR / f"{chain}.responses.json.gz",
                   {"chain": chain, "scope": SCOPES[chain], "recorded_at": recorded_at, "calls": calls})
        got = result(chain, replay(chain))
        _write(FIXTURE_DIR / f"{chain}.expected.json.gz", got)
        found = problems(chain, got)
        bad |= bool(found)
        print(f"{chain}: {len(got['rows'])} funciones, {len(got['cinemas'])} cines, {len(got['units'])} unidades"
              + "".join(f"\n  PROBLEMA {p}" for p in found))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
