"""Ejecuta un snapshot de la plaza piloto para una o ambas cadenas.

Uso:
  python3 -m scraper.run                # ambas cadenas
  python3 -m scraper.run --chain cinemex
  python3 -m scraper.run --no-raw       # no guardar el crudo comprimido
"""
import argparse
import sys
import time
import traceback
from collections import Counter
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


def run_chain(conn, chain, save_raw=True):
    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    snapshot_id = store.begin_snapshot(conn, chain, taken_at)
    try:
        raw = SNAPSHOTTERS[chain]()
        rows = normalize.rows(chain, raw)
        current = {r["show_id"]: r for r in rows}
        prev_id, previous = store.load_current(conn, chain)
        events = diff.diff(chain, previous, current, snapshot_id, prev_id, taken_at) if prev_id else []
        raw_path = store.save_raw(chain, taken_at, raw) if save_raw else None
        store.replace_current(conn, chain, snapshot_id, rows, previous, taken_at)
        store.insert_events(conn, events)
        n_cinemas = len({r["cinema_id"] for r in rows})
        store.finish_snapshot(conn, snapshot_id, ok=1, n_shows=len(rows), n_cinemas=n_cinemas,
                              n_events=len(events), calls=raw.get("calls"),
                              duration_s=round(time.time() - t0, 1), raw_path=raw_path)
        kinds = Counter(e["kind"] for e in events)
        detail = "baseline" if not prev_id else (", ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "none")
        summary = (f"{chain} ok snapshot={snapshot_id} cinemas={n_cinemas} shows={len(rows)} "
                   f"events={len(events)} ({detail}) calls={raw.get('calls')} dur={time.time() - t0:.0f}s")
        log(summary)
        return True
    except Exception as e:  # noqa: BLE001 - queremos registrar cualquier fallo y seguir con la otra cadena
        hint = ""
        if isinstance(e, Blocked):
            hint = " (la IP de salida está bloqueada por el WAF, no es la clave; ver project.md > Consideraciones)"
        elif isinstance(e, AuthError):
            hint = " (¿rotó la clave? ver project.md > Consideraciones)"
        store.finish_snapshot(conn, snapshot_id, ok=0, duration_s=round(time.time() - t0, 1),
                              error=f"{type(e).__name__}: {e}"[:2000])
        log(f"{chain} FAIL snapshot={snapshot_id} {type(e).__name__}: {e}{hint}")
        log(traceback.format_exc().strip().splitlines()[-1])
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chain", choices=sorted(SNAPSHOTTERS), action="append",
                        help="cadena a procesar (repetible); por defecto ambas")
    parser.add_argument("--no-raw", action="store_true", help="no guardar el crudo comprimido")
    args = parser.parse_args(argv)
    chains = args.chain or sorted(SNAPSHOTTERS)
    conn = store.connect()
    ok = all([run_chain(conn, c, save_raw=not args.no_raw) for c in chains])
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
