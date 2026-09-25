"""Unidades de captura: la cartelera de una cadena se descarga por partes que fallan por separado.

Cinemex por estado de su API (`cinemas/state/{id}`); Cinépolis por lotes de hasta 30 cines agrupados por estado de INEGI
(`pack_by_state`), porque su API recibe listas de cines y no tiene estados. Una unidad que falla (tras los reintentos por
petición de `http.py` y `UNIT_RETRIES` de la unidad completa) no tumba a las demás: queda registrada con su error y su
alcance, y `run.py` conserva el estado anterior de sus cines en vez de darlos por cancelados (`diff.carry_over`).

Los errores del sistema (`AuthError`: clave rotada; `Blocked`: WAF; `RateLimited`: 429 tras reintentos) no son de una
unidad: detienen la cadena, porque las demás unidades fallarían igual y seguir solo insiste contra la API.

Cada unidad es un dict con `unit` (llave estable entre capturas), `label` (texto para Operaciones) y su alcance
(`state_ids`, `city_ids` o `cinema_ids`, lo que se sepa antes de descargar). `run_units` le añade `ok`, `error`,
`attempts`, `calls` y `duration_s`. Solo librería estándar.
"""
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .http import ApiError, AuthError, Blocked, RateLimited

SYSTEMIC = (AuthError, Blocked, RateLimited)


def _attempt(unit, fetch):
    stats = {"calls": 0}
    t0 = time.time()
    try:
        data = fetch(unit, stats)
        error = None
    except SYSTEMIC:
        raise
    except Exception as e:  # noqa: BLE001 - cualquier fallo de una unidad se registra y no tumba a las demás
        data, error = None, f"{type(e).__name__}: {e}"[:1000]
    return data, error, stats["calls"], time.time() - t0


def run_units(units, fetch, workers=1, retries=None):
    """Corre `fetch(unit, stats)` por unidad, con `workers` hilos, y reintenta `retries` veces las que fallaron.
    Devuelve [(registro de la unidad, datos | None)] en el orden de `units`. Levanta la primera excepción de
    `SYSTEMIC` que aparezca y `ApiError` si fallaron todas."""
    retries = config.UNIT_RETRIES if retries is None else retries
    records = [dict(u, ok=False, error=None, attempts=0, calls=0, duration_s=0.0) for u in units]
    data = [None] * len(units)
    abort = threading.Event()

    def one(i):
        if abort.is_set():
            return i, None, "cancelada: la cadena se detuvo", 0, 0.0
        return (i, *_attempt(units[i], fetch))

    pending = list(range(len(units)))
    for attempt in range(retries + 1):
        if not pending:
            break
        failed = []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(one, i) for i in pending]
            try:
                for fut in as_completed(futures):
                    i, got, error, calls, secs = fut.result()
                    rec = records[i]
                    rec["attempts"] += 1
                    rec["calls"] += calls
                    rec["duration_s"] = round(rec["duration_s"] + secs, 1)
                    rec["ok"], rec["error"] = error is None, error
                    data[i] = got
                    if error is not None:
                        failed.append(i)
            except SYSTEMIC:
                abort.set()
                for f in futures:
                    f.cancel()
                raise
        pending = sorted(failed)
    if units and not any(r["ok"] for r in records):
        raise ApiError(f"fallaron las {len(units)} unidades; la primera: {records[0]['error']}")
    return list(zip(records, data))


def pack_by_state(cinemas, size=None):
    """Agrupa cines (dicts con `id` y `state_code`) en lotes de hasta `size` por estado de INEGI.

    Un estado con más de `size` cines se parte en lotes parejos que van solos (CDMX, 51 cines: 26 + 25); los estados
    completos se acomodan, en orden de clave, en el primer lote donde caben, así los chicos comparten lote y el reparto
    es el mismo mientras no cambien los cines. Devuelve [{"unit", "state_codes", "parts", "cinema_ids"}]; `parts` dice qué
    pedazo de cada estado lleva (`{"09": "1/2"}`)."""
    size = size or config.CINEPOLIS_BATCH_SIZE
    by_state = {}
    for c in sorted(cinemas, key=lambda c: c["id"]):
        by_state.setdefault(c.get("state_code") or "", []).append(c["id"])
    pieces = []
    for code in sorted(by_state, key=lambda k: (k == "", k)):
        ids = by_state[code]
        n = math.ceil(len(ids) / size)
        step = math.ceil(len(ids) / n)
        for i in range(n):
            pieces.append((code, f"{i + 1}/{n}" if n > 1 else "", ids[i * step:(i + 1) * step]))
    batches = []
    for code, part, ids in pieces:
        # Las partes de un estado partido van solas, para que un fallo se lea "Ciudad de México (1/2)"; los estados
        # completos comparten lote entre sí.
        target = None if part else next((b for b in batches if not b["split"] and len(b["cinema_ids"]) + len(ids) <= size), None)
        if target is None:
            target = {"state_codes": [], "parts": {}, "cinema_ids": [], "split": bool(part)}
            batches.append(target)
        target["state_codes"].append(code)
        target["parts"][code] = part
        target["cinema_ids"].extend(ids)
    for b in batches:
        del b["split"]
        b["unit"] = "+".join(f"{c or 'sin-estado'}{'-' + b['parts'][c].replace('/', 'de') if b['parts'][c] else ''}"
                             for c in b["state_codes"])
    return batches
