"""Copia por marca de agua de las tablas de SQLite que solo crecen (snapshot, event, muestreos y aforo)."""
import json

from scraper import config
from scraper.normalize import TRACKED_FIELDS

from . import pg

BATCH = 5000


def _bucket_path(raw_path):
    """`data/raw/{chain}/{fecha}/{archivo}` → `s3://bucket/raw/...` si hay bucket (así lo sube backup.sh)."""
    if raw_path and config.BACKUP_BUCKET and raw_path.startswith("data/raw/"):
        return f"{config.BACKUP_BUCKET.rstrip('/')}/raw/{raw_path[len('data/raw/'):]}"
    return raw_path


def copy_snapshots(sq, cur):
    """Copia los snapshots nuevos. Uno sin cerrar (`ok` NULL) reciente detiene la copia ahí: está en curso. Uno sin
    cerrar más viejo que `config.SNAPSHOT_STALE_HOURS` se da por fallido (el scraper murió sin finish_snapshot)."""
    wm = pg.watermark(cur, "snapshot")
    rows = sq.execute("SELECT * FROM snapshot WHERE id > ? ORDER BY id", (wm,)).fetchall()
    stale = f"-{int(config.SNAPSHOT_STALE_HOURS)} hours"
    out, last = [], wm
    for r in rows:
        ok, error = r["ok"], r["error"]
        if ok is None:
            is_stale = sq.execute("SELECT ? < strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)", (r["taken_at"][:19], stale)).fetchone()[0]
            if not is_stale:
                break
            ok, error = 0, "sin finish_snapshot (el scraper no cerró la captura)"
        out.append((r["id"], r["chain"], pg.to_ts(r["taken_at"]), pg.to_ts(r["finished_at"]), bool(ok), r["n_shows"], r["n_cinemas"],
                    r["n_events"], r["calls"], r["duration_s"], _bucket_path(r["raw_path"]), error))
        last = r["id"]
    if out:
        cur.executemany("""INSERT INTO snapshot (id, chain, taken_at, finished_at, ok, n_shows, n_cinemas, n_events, calls, duration_s, raw_path, error)
                           VALUES (%s, %s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""", out)
        pg.set_watermark(cur, "snapshot", last)
    return len(out)


def pending_snapshots(sq, cur):
    """Capturas buenas (con crudo) aún no reconstruidas en showtime/showtime_state, en orden."""
    wm = pg.watermark(cur, "showtime")
    return [dict(r) for r in sq.execute(
        "SELECT id, chain, taken_at, raw_path FROM snapshot WHERE ok = 1 AND raw_path IS NOT NULL AND id > ? ORDER BY id", (wm,))]


def event_changes(before_json, after_json):
    """{campo: [antes, después]} sobre TRACKED_FIELDS; None en altas y cierres (un solo lado)."""
    if not before_json or not after_json:
        return None
    before, after = json.loads(before_json), json.loads(after_json)
    return {f: [before.get(f), after.get(f)] for f in TRACKED_FIELDS if (before.get(f) or None) != (after.get(f) or None)} or None


def copy_events(sq, cur):
    """Eventos nuevos cuyo snapshot ya está en Postgres (llave foránea)."""
    wm = pg.watermark(cur, "event")
    max_snap = pg.watermark(cur, "snapshot")
    rows = sq.execute("SELECT * FROM event WHERE id > ? AND snapshot_id <= ? ORDER BY id LIMIT ?", (wm, max_snap, BATCH)).fetchall()
    total = 0
    while rows:
        pg.ensure_partitions(cur, "event", [pg.to_ts(r["detected_at"]) for r in rows], column_kind="timestamptz")
        cur.executemany("""INSERT INTO event (id, chain, show_id, show_date, kind, detected_at, snapshot_id, prev_snapshot_id, cinema_id, movie_id, changes)
                           VALUES (%s, %s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id, detected_at) DO NOTHING""",
                        [(r["id"], r["chain"], r["show_id"], pg.to_date(r["date"]), r["kind"], pg.to_ts(r["detected_at"]), r["snapshot_id"],
                          r["prev_snapshot_id"], r["cinema_id"], r["movie_id"],
                          json.dumps(event_changes(r["before_json"], r["after_json"]), ensure_ascii=False) if event_changes(r["before_json"], r["after_json"]) else None)
                         for r in rows])
        wm = rows[-1]["id"]; total += len(rows)
        pg.set_watermark(cur, "event", wm)
        rows = sq.execute("SELECT * FROM event WHERE id > ? AND snapshot_id <= ? ORDER BY id LIMIT ?", (wm, max_snap, BATCH)).fetchall()
    return total


# Tablas de muestreo: (sql de inserción, conversor de fila SQLite → tupla).
SAMPLES = {
    "occupancy_sample": ("""INSERT INTO occupancy_sample (id, chain, show_id, show_date, cinema_id, screen, movie_id, starts_at, sampled_at,
                                minutes_to_start, seats, sold, broken, sold_pct, availability)
                            VALUES (%s, %s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                         lambda r: (r["id"], r["chain"], r["show_id"], pg.to_date(r["datetime_local"]), r["cinema_id"], r["screen"], r["movie_id"],
                                    pg.to_local(r["datetime_local"]), pg.to_ts(r["sampled_at"]), r["minutes_to_start"], r["seats"], r["sold"], r["broken"],
                                    r["sold_pct"], r["availability"] or None)),
    "price_sample": ("""INSERT INTO price_sample (id, chain, show_id, cinema_id, screen, format_bucket, day_type, show_date, starts_at, sampled_at,
                            general_cents, min_cents, max_cents, fee_cents, tickets)
                        VALUES (%s, %s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                     lambda r: (r["id"], r["chain"], r["show_id"], r["cinema_id"], r["screen"], r["format_bucket"], r["day_type"], pg.to_date(r["date"]),
                                pg.to_local(r["datetime_local"]), pg.to_ts(r["sampled_at"]), r["general_cents"], r["min_cents"], r["max_cents"],
                                r["fee_cents"], r["tickets_json"])),
    "concession_price": ("""INSERT INTO concession_price (id, chain, cinema_id, sampled_at, category, sub_category, product_id, product_name, price_cents,
                                product_structure, promotion_type, active)
                            VALUES (%s, %s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                         lambda r: (r["id"], r["chain"], r["cinema_id"], pg.to_ts(r["sampled_at"]), r["category"], r["sub_category"], r["product_id"],
                                    r["product_name"] or r["product_id"], r["price_cents"] or 0, r["product_structure"], r["promotion_type"],
                                    bool(r["active"]) if r["active"] is not None else None)),
    "delivery_price": ("""INSERT INTO delivery_price (id, platform, chain, store_id, store_slug, store_name, address, lat, lng, status, available, sampled_at,
                              category, product_id, product_name, price_cents, description, in_stock)
                          VALUES (%s, %s, %s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                       lambda r: (r["id"], r["platform"], r["chain"], r["store_id"], r["store_slug"], r["store_name"], r["address"], pg.to_float(r["lat"]),
                                  pg.to_float(r["lng"]), r["status"], bool(r["available"]) if r["available"] is not None else None, pg.to_ts(r["sampled_at"]),
                                  r["category"], r["product_id"], r["product_name"], r["price_cents"], r["description"],
                                  bool(r["in_stock"]) if r["in_stock"] is not None else None)),
}


def copy_by_id(sq, cur, table):
    """Copia las filas nuevas de una tabla de muestreo por marca de agua `id`, en lotes."""
    insert_sql, convert = SAMPLES[table]
    wm = pg.watermark(cur, table)
    total = 0
    while True:
        rows = sq.execute(f"SELECT * FROM {table} WHERE id > ? ORDER BY id LIMIT ?", (wm, BATCH)).fetchall()
        if not rows:
            return total
        cur.executemany(insert_sql, [convert(r) for r in rows])
        wm = rows[-1]["id"]; total += len(rows)
        pg.set_watermark(cur, table, wm)


def copy_auditoriums(sq, cur):
    """El aforo en SQLite se sobreescribe por sala; en Postgres se guarda una fila por medición distinta."""
    cur.execute("""SELECT DISTINCT ON (chain, cinema_id, screen) chain::text, cinema_id, screen, seats, broken
                   FROM auditorium ORDER BY chain, cinema_id, screen, sampled_at DESC""")
    latest = {(r[0], r[1], r[2]): (r[3], r[4]) for r in cur.fetchall()}
    out = []
    for r in sq.execute("SELECT * FROM auditorium").fetchall():
        key = (r["chain"], r["cinema_id"], r["screen"])
        if r["seats"] is None or latest.get(key) == (r["seats"], r["broken"] or 0):
            continue
        out.append((r["chain"], r["cinema_id"], r["screen"], pg.to_ts(r["sampled_at"]), r["seats"], r["broken"] or 0, r["areas_json"], r["session_id"]))
    if out:
        cur.executemany("""INSERT INTO auditorium (chain, cinema_id, screen, sampled_at, seats, broken, areas, session_id)
                           VALUES (%s::chain_t, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (chain, cinema_id, screen, sampled_at) DO NOTHING""", out)
    return len(out)
