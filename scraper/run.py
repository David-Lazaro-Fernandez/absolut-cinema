"""Ejecuta un snapshot de cartelera para una o ambas cadenas (alcance nacional por defecto; ver config).

Uso:
  python3 -m scraper.run                # ambas cadenas
  python3 -m scraper.run --chain cinemex
  python3 -m scraper.run --no-raw       # no guardar el crudo comprimido

Las cadenas se descargan en paralelo (son APIs distintas y la descarga nacional tarda 15–25 min cada una) y se
escriben en serie: la base tiene un solo escritor y la escritura de una captura dura segundos.
"""
import argparse
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import cinemex, cinepolis, config, diff, normalize, store
from .http import AuthError, Blocked

SNAPSHOTTERS = {"cinepolis": cinepolis.snapshot, "cinemex": cinemex.snapshot}


def log(msg):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(config.LOG_DIR / "run.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def fetch(chain):
    """Descarga el crudo de una cadena. Solo red: no toca la base. Devuelve (crudo | None, error | None, segundos)."""
    t0 = time.time()
    try:
        return SNAPSHOTTERS[chain](), None, time.time() - t0
    except Exception as e:  # noqa: BLE001 - cualquier fallo de una cadena se registra y no tumba a la otra
        return None, e, time.time() - t0


def _units(chain, raw):
    return len(raw.get("city_ids") or []) if chain == "cinepolis" else len(raw.get("state_ids") or [])


def commit(conn, chain, snapshot_id, taken_at, raw, fetch_s, save_raw=True):
    """Normaliza, compara con el estado anterior y escribe la captura. Devuelve True si quedó bien."""
    t0 = time.time()
    try:
        rows = normalize.rows(chain, raw)
        current = {r["show_id"]: r for r in rows}
        prev_id, previous = store.load_current(conn, chain)
        events = diff.diff(chain, previous, current, snapshot_id, prev_id, taken_at) if prev_id else []
        raw_path = store.save_raw(chain, taken_at, raw) if save_raw else None
        store.replace_current(conn, chain, snapshot_id, rows, previous, taken_at)
        store.upsert_cinemas(conn, normalize.cinemas(chain, raw), taken_at)
        store.insert_events(conn, events)
        n_cinemas = len({r["cinema_id"] for r in rows})
        store.finish_snapshot(conn, snapshot_id, ok=1, n_shows=len(rows), n_cinemas=n_cinemas,
                              n_events=len(events), calls=raw.get("calls"),
                              duration_s=round(fetch_s + time.time() - t0, 1), raw_path=raw_path)
        kinds = Counter(e["kind"] for e in events)
        detail = "baseline" if not prev_id else (", ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "none")
        unit = "cities" if chain == "cinepolis" else "states"
        log(f"{chain} ok snapshot={snapshot_id} {unit}={_units(chain, raw)} cinemas={n_cinemas} shows={len(rows)} "
            f"events={len(events)} ({detail}) calls={raw.get('calls')} fetch={fetch_s:.0f}s write={time.time() - t0:.0f}s")
        return True
    except Exception as e:  # noqa: BLE001 - idem: registrar y seguir con la otra cadena
        fail(conn, chain, snapshot_id, e, fetch_s + time.time() - t0)
        return False


def fail(conn, chain, snapshot_id, error, duration_s):
    hint = ""
    if isinstance(error, Blocked):
        hint = " (la IP de salida está bloqueada por el WAF, no es la clave; ver project.md > Consideraciones)"
    elif isinstance(error, AuthError):
        hint = " (¿rotó la clave? ver project.md > Consideraciones)"
    store.finish_snapshot(conn, snapshot_id, ok=0, duration_s=round(duration_s, 1),
                          error=f"{type(error).__name__}: {error}"[:2000])
    log(f"{chain} FAIL snapshot={snapshot_id} {type(error).__name__}: {error}{hint}")
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    log(tb[-1].strip() if len(tb) < 2 else "".join(tb[-2:]).strip().splitlines()[-1])


def run(conn, chains, save_raw=True):
    """Captura de varias cadenas: `begin_snapshot` de todas, descarga en paralelo, escritura en serie."""
    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ids = {chain: store.begin_snapshot(conn, chain, taken_at) for chain in chains}
    with ThreadPoolExecutor(max_workers=len(chains)) as pool:
        results = dict(zip(chains, pool.map(fetch, chains)))
    ok = True
    for chain in chains:
        raw, error, fetch_s = results[chain]
        if error is not None:
            fail(conn, chain, ids[chain], error, fetch_s)
            ok = False
            continue
        ok &= commit(conn, chain, ids[chain], taken_at, raw, fetch_s, save_raw=save_raw)
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chain", choices=sorted(SNAPSHOTTERS), action="append",
                        help="cadena a procesar (repetible); por defecto ambas")
    parser.add_argument("--no-raw", action="store_true", help="no guardar el crudo comprimido")
    args = parser.parse_args(argv)
    chains = args.chain or sorted(SNAPSHOTTERS)
    conn = store.connect()
    ok = run(conn, chains, save_raw=not args.no_raw)
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
