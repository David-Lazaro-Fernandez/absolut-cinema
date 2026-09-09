"""Sincroniza data/snapshots.db con el archivo histórico en PostgreSQL.

Uso: .venv/bin/python -m sync.run [--dry-run] [--limit N] [--status-only]
Orden: snapshots → historia de funciones (una transacción por captura) → eventos → muestreos → aforo → estado en
`config.SYNC_STATUS_PATH` (lo lee scraper.health, que no tiene psycopg). Idempotente: todo va por marca de agua y
`ON CONFLICT DO NOTHING`; si muere a mitad de una captura, esa transacción se deshace y la siguiente corrida la rehace
desde el mismo crudo. Sin marcas de agua, la primera corrida es la carga inicial completa. Sale con 1 si hubo error.
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from scraper import config

from . import copy, pg, state


def log(msg):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(config.LOG_DIR / "sync.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def open_sqlite():
    if not config.DB_PATH.exists():
        raise FileNotFoundError(f"no existe {config.DB_PATH}")
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def lag(sq, cur):
    """Cuánto falta por copiar, por tabla: capturas buenas pendientes y diferencia de ids."""
    out = {"showtime": len(copy.pending_snapshots(sq, cur))}
    for table in ("snapshot", "event", *copy.SAMPLES):
        mx = sq.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0]
        out[table] = int(mx) - pg.watermark(cur, table)
    return out


def write_status(status):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    config.SYNC_STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="solo informa cuánto falta por copiar")
    ap.add_argument("--limit", type=int, help="máximo de capturas a reconstruir en esta corrida")
    ap.add_argument("--status-only", action="store_true", help="imprime el último estado escrito y sale")
    a = ap.parse_args(argv)
    if a.status_only:
        print(config.SYNC_STATUS_PATH.read_text() if config.SYNC_STATUS_PATH.exists() else "sin estado")
        return 0
    t0 = time.time()
    status = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": False, "error": None, "counts": {}}
    sq = open_sqlite()
    try:
        with pg.connect() as conn:
            cur = conn.cursor()
            if a.dry_run:
                status["lag"] = lag(sq, cur); status["ok"] = True
                log(f"sync dry-run: pendiente {status['lag']}")
                print(json.dumps(status["lag"]))
                return 0
            n = copy.copy_snapshots(sq, cur); conn.commit(); status["counts"]["snapshot"] = n
            pending = copy.pending_snapshots(sq, cur)
            if a.limit:
                pending = pending[:a.limit]
            open_by_chain = {}
            done = 0
            for snap in pending:
                try:
                    counts = state.process_snapshot(cur, snap, open_by_chain)
                    conn.commit(); done += 1
                    log(f"sync showtime snapshot {snap['id']} {snap['chain']} {snap['taken_at']}: {counts}")
                except FileNotFoundError as e:
                    conn.rollback()
                    raise RuntimeError(f"falta el crudo del snapshot {snap['id']} ({snap['raw_path']}); no se puede saltar sin romper la historia") from e
            status["counts"]["showtime_snapshots"] = done
            n = copy.copy_events(sq, cur); conn.commit(); status["counts"]["event"] = n
            for table in copy.SAMPLES:
                n = copy.copy_by_id(sq, cur, table); conn.commit(); status["counts"][table] = n
            n = copy.copy_auditoriums(sq, cur); conn.commit(); status["counts"]["auditorium"] = n
            status["watermarks"] = {t: pg.watermark(cur, t) for t in ("snapshot", "showtime", "event", *copy.SAMPLES)}
            status["lag"] = lag(sq, cur)
            status["ok"] = True
    except Exception as e:   # el estado debe quedar escrito aunque falle: es lo que lee la salud
        status["error"] = f"{type(e).__name__}: {e}"[:500]
        log(f"sync FAIL {status['error']}")
    finally:
        sq.close()
        status["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status["duration_s"] = round(time.time() - t0, 1)
        write_status(status)
    log(f"sync done in {status['duration_s']}s ok={status['ok']} counts={status['counts']} lag={status.get('lag')}")
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
