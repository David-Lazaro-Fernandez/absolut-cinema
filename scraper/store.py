"""Persistencia en SQLite: metadatos de snapshots, estado actual por cadena y eventos de cambio."""
import gzip
import json
import sqlite3
from datetime import datetime

from . import config
from .normalize import CINEMA_COLUMNS, COLUMNS

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot (
  id INTEGER PRIMARY KEY,
  chain TEXT NOT NULL,
  taken_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER,
  n_shows INTEGER,
  n_cinemas INTEGER,
  n_events INTEGER,
  calls INTEGER,
  duration_s REAL,
  raw_path TEXT,
  error TEXT,
  n_units INTEGER,
  n_failed_units INTEGER
);
-- Unidades de una captura (scraper/units.py): un estado de Cinemex o un lote de cines de Cinépolis por estado de INEGI,
-- con su resultado. Una unidad fallida conserva el estado anterior de sus cines (`carried`: funciones conservadas).
CREATE TABLE IF NOT EXISTS snapshot_unit (
  snapshot_id INTEGER NOT NULL,
  chain TEXT NOT NULL,
  unit TEXT NOT NULL,
  label TEXT,
  ok INTEGER NOT NULL,
  error TEXT,
  attempts INTEGER,
  calls INTEGER,
  duration_s REAL,
  n_cinemas INTEGER,
  n_shows INTEGER,
  carried INTEGER,
  PRIMARY KEY (snapshot_id, unit)
);
CREATE TABLE IF NOT EXISTS current_showtime (
  chain TEXT NOT NULL,
  show_id TEXT NOT NULL,
  snapshot_id INTEGER NOT NULL,
  first_seen TEXT NOT NULL,
  %s,
  PRIMARY KEY (chain, show_id)
);
CREATE TABLE IF NOT EXISTS event (
  id INTEGER PRIMARY KEY,
  chain TEXT NOT NULL,
  show_id TEXT NOT NULL,
  kind TEXT NOT NULL,          -- added | removed | expired | moved | changed | availability
  detected_at TEXT NOT NULL,
  snapshot_id INTEGER NOT NULL,
  prev_snapshot_id INTEGER,
  cinema_id TEXT, movie_id TEXT, movie_title TEXT, date TEXT, datetime_local TEXT,
  before_json TEXT,
  after_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_detected ON event (chain, detected_at);
CREATE INDEX IF NOT EXISTS idx_event_show ON event (chain, show_id);
-- Reconstrucción de la cartelera de un cine y un día en un momento dado (analytics/history.py).
CREATE INDEX IF NOT EXISTS idx_event_board ON event (chain, cinema_id, date, id);
CREATE INDEX IF NOT EXISTS idx_current_cinema ON current_showtime (chain, cinema_id, date);
-- Dimensión de cines vista en las capturas: la llave geográfica de cada API (`city_id`: Cinépolis ciudad, Cinemex área),
-- el estado de Cinemex, el estado de INEGI de ambas cadenas (`state_code`), la zona horaria (solo Cinépolis la publica) y
-- el vistaId de Cinépolis. Por aquí se acotan por
-- plaza las tablas de muestreo, que no llevan geografía propia.
CREATE TABLE IF NOT EXISTS cinema (
  chain TEXT NOT NULL, cinema_id TEXT NOT NULL, name TEXT, lat REAL, lng REAL,
  city_id TEXT, state_id TEXT, state_code TEXT, timezone TEXT, vista_id TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  PRIMARY KEY (chain, cinema_id)
);
CREATE INDEX IF NOT EXISTS idx_cinema_city ON cinema (chain, city_id);
-- Aforo por sala (Cinépolis desde el plano de asientos; Cinemex llegará del cliente).
CREATE TABLE IF NOT EXISTS auditorium (
  chain TEXT NOT NULL, cinema_id TEXT NOT NULL, screen TEXT NOT NULL,
  seats INTEGER, broken INTEGER, areas_json TEXT, session_id TEXT, sampled_at TEXT,
  PRIMARY KEY (chain, cinema_id, screen)
);
-- Muestreo de ocupación: un plano de asientos por función a N minutos de empezar.
CREATE TABLE IF NOT EXISTS occupancy_sample (
  id INTEGER PRIMARY KEY,
  chain TEXT NOT NULL, show_id TEXT NOT NULL, cinema_id TEXT, screen TEXT, movie_id TEXT, movie_title TEXT,
  datetime_local TEXT, sampled_at TEXT NOT NULL, minutes_to_start INTEGER,
  seats INTEGER, sold INTEGER, broken INTEGER, sold_pct REAL, availability TEXT
);
CREATE INDEX IF NOT EXISTS idx_occ_show ON occupancy_sample (chain, show_id);
CREATE INDEX IF NOT EXISTS idx_occ_time ON occupancy_sample (chain, datetime_local);
-- Muestreo de precios: una función por cine, cubeta de formato y tipo de día.
CREATE TABLE IF NOT EXISTS price_sample (
  id INTEGER PRIMARY KEY,
  chain TEXT NOT NULL, show_id TEXT NOT NULL, cinema_id TEXT, screen TEXT, format_bucket TEXT, day_type TEXT,
  date TEXT, datetime_local TEXT, sampled_at TEXT NOT NULL,
  general_cents INTEGER, min_cents INTEGER, max_cents INTEGER, fee_cents INTEGER, tickets_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_price_key ON price_sample (chain, cinema_id, format_bucket, day_type, date);
-- Dulcería: menú completo por cine (Cinépolis vía fab-struct-concession; Cinemex llegará del cliente).
CREATE TABLE IF NOT EXISTS concession_price (
  id INTEGER PRIMARY KEY,
  chain TEXT NOT NULL, cinema_id TEXT NOT NULL, sampled_at TEXT NOT NULL,
  category TEXT, sub_category TEXT, product_id TEXT, product_name TEXT, price_cents INTEGER,
  product_structure TEXT, promotion_type TEXT, active INTEGER
);
CREATE INDEX IF NOT EXISTS idx_conc_cinema ON concession_price (chain, cinema_id, sampled_at);
-- Preventas de Cinemex: panel fijo de funciones por título, releídas a diario (scraper/presale.py).
CREATE TABLE IF NOT EXISTS presale_sample (
  id INTEGER PRIMARY KEY,
  chain TEXT NOT NULL, show_id TEXT NOT NULL, movie_id TEXT, movie_title TEXT, title_norm TEXT,
  cinema_id TEXT, screen TEXT, date TEXT, datetime_local TEXT, datetime_utc TEXT, release_date TEXT,
  sampled_at TEXT NOT NULL, days_to_start REAL, seats INTEGER, sold INTEGER
);
CREATE INDEX IF NOT EXISTS idx_presale_show ON presale_sample (chain, show_id, sampled_at);
CREATE INDEX IF NOT EXISTS idx_presale_title ON presale_sample (chain, title_norm, sampled_at);
-- Dulcería a domicilio (Rappi, DiDi Food): catálogo por tienda; ver scraper/delivery.py.
CREATE TABLE IF NOT EXISTS delivery_price (
  id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL, chain TEXT NOT NULL, store_id TEXT NOT NULL, store_slug TEXT, store_name TEXT, address TEXT,
  lat REAL, lng REAL, status TEXT, available INTEGER, sampled_at TEXT NOT NULL,
  category TEXT, product_id TEXT, product_name TEXT, price_cents INTEGER, description TEXT, in_stock INTEGER
);
CREATE INDEX IF NOT EXISTS idx_delivery_store ON delivery_price (platform, store_id, sampled_at);
""" % ",\n  ".join(f"{c} TEXT" if c not in ("lat", "lng", "duration_min") else f"{c} REAL" for c in COLUMNS if c not in ("chain", "show_id"))

ROW_COLUMNS = [c for c in COLUMNS if c not in ("chain", "show_id")]
_REAL_COLUMNS = ("lat", "lng", "duration_min")
CINEMA_ROW_COLUMNS = [c for c in CINEMA_COLUMNS if c not in ("chain", "cinema_id")]


def migrate(conn):
    """Cambios de esquema aditivos sobre una base ya creada: columnas de `COLUMNS` y `CINEMA_COLUMNS` que aún no
    existen en `current_showtime` y `cinema` (la base de producción tiene historia desde el 2026-09-07 y no se recrea)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(current_showtime)")}
    for col in ROW_COLUMNS:
        if col not in have:
            kind = "REAL" if col in ("lat", "lng", "duration_min") else "TEXT"
            conn.execute(f"ALTER TABLE current_showtime ADD COLUMN {col} {kind}")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(snapshot)")}
    for col in ("n_units", "n_failed_units"):
        if col not in have:
            conn.execute(f"ALTER TABLE snapshot ADD COLUMN {col} INTEGER")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(cinema)")}
    for col in CINEMA_ROW_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE cinema ADD COLUMN {col} {'REAL' if col in ('lat', 'lng') else 'TEXT'}")
    conn.commit()


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    migrate(conn)
    return conn


def begin_snapshot(conn, chain, taken_at):
    cur = conn.execute("INSERT INTO snapshot (chain, taken_at) VALUES (?, ?)", (chain, taken_at))
    conn.commit()
    return cur.lastrowid


def finish_snapshot(conn, snapshot_id, **fields):
    fields["finished_at"] = datetime.utcnow().isoformat(timespec="seconds") + "+00:00"
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE snapshot SET {sets} WHERE id = ?", (*fields.values(), snapshot_id))
    conn.commit()


def load_current(conn, chain):
    """Estado actual de la cadena: (snapshot_id del último snapshot ok, {show_id: fila})."""
    row = conn.execute(
        "SELECT id FROM snapshot WHERE chain = ? AND ok = 1 ORDER BY id DESC LIMIT 1", (chain,)
    ).fetchone()
    if not row:
        return None, {}
    rows = conn.execute("SELECT * FROM current_showtime WHERE chain = ?", (chain,)).fetchall()
    state = {}
    for r in rows:
        d = {k: r[k] for k in COLUMNS}
        d["first_seen"] = r["first_seen"]
        state[r["show_id"]] = d
    return row["id"], state


def _stored(col, value):
    # El valor como lo guarda SQLite según la afinidad de la columna, para comparar con lo leído de la base sin que
    # 3 contra "3" o 100 contra 100.0 cuenten como cambio.
    if value is None:
        return None
    if col in _REAL_COLUMNS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return str(value)


def apply_current(conn, chain, snapshot_id, rows, previous, taken_at, keep=()):
    """Deja current_showtime igual que `rows` escribiendo solo la diferencia con `previous` (el estado cargado con
    `load_current`): inserta las funciones nuevas, actualiza las que cambiaron en cualquier columna y borra las que ya
    no están, salvo las de `keep` (funciones de una unidad fallida, que se conservan tal cual). `first_seen` se
    conserva; `snapshot_id` es la última captura que escribió la fila. Devuelve {inserted, updated, deleted}."""
    current = {r["show_id"] for r in rows}
    gone = [(chain, sid) for sid in previous if sid not in current and sid not in keep]
    conn.executemany("DELETE FROM current_showtime WHERE chain = ? AND show_id = ?", gone)
    new, changed = [], []
    for r in rows:
        prev = previous.get(r["show_id"])
        values = [_stored(c, r.get(c)) for c in ROW_COLUMNS]
        if prev is None:
            new.append([chain, r["show_id"], snapshot_id, taken_at] + values)
        elif any(_stored(c, prev.get(c)) != v for c, v in zip(ROW_COLUMNS, values)):
            changed.append([snapshot_id] + values + [chain, r["show_id"]])
    cols = ["chain", "show_id", "snapshot_id", "first_seen"] + ROW_COLUMNS
    conn.executemany(f"INSERT INTO current_showtime ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", new)
    sets = ", ".join(f"{c} = ?" for c in ["snapshot_id"] + ROW_COLUMNS)
    conn.executemany(f"UPDATE current_showtime SET {sets} WHERE chain = ? AND show_id = ?", changed)
    return {"inserted": len(new), "updated": len(changed), "deleted": len(gone)}


def insert_units(conn, chain, snapshot_id, units):
    """Una fila por unidad de la captura (`scraper/units.py`), con las funciones leídas y conservadas de cada una."""
    conn.executemany(
        """INSERT INTO snapshot_unit (snapshot_id, chain, unit, label, ok, error, attempts, calls, duration_s,
                                      n_cinemas, n_shows, carried)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(snapshot_id, chain, u["unit"], u.get("label"), int(bool(u.get("ok"))), u.get("error"), u.get("attempts"),
          u.get("calls"), u.get("duration_s"), u.get("n_cinemas"), u.get("n_shows"), u.get("carried")) for u in units])


def upsert_cinemas(conn, cinemas, taken_at):
    """Alta o refresco de la dimensión de cines (`normalize.cinemas`): conserva `first_seen` y no pisa con NULL lo que
    ya se sabía (Cinemex no publica zona horaria; un cine sin coordenadas un día las recupera al siguiente)."""
    cols = ["chain", "cinema_id"] + CINEMA_ROW_COLUMNS + ["first_seen", "last_seen"]
    sets = ", ".join(f"{c} = COALESCE(excluded.{c}, cinema.{c})" for c in CINEMA_ROW_COLUMNS)
    conn.executemany(
        f"""INSERT INTO cinema ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})
            ON CONFLICT (chain, cinema_id) DO UPDATE SET {sets}, last_seen = excluded.last_seen""",
        [[c["chain"], c["cinema_id"]] + [c.get(k) for k in CINEMA_ROW_COLUMNS] + [taken_at, taken_at] for c in cinemas])


def insert_events(conn, events):
    conn.executemany(
        """INSERT INTO event (chain, show_id, kind, detected_at, snapshot_id, prev_snapshot_id,
                              cinema_id, movie_id, movie_title, date, datetime_local, before_json, after_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(e["chain"], e["show_id"], e["kind"], e["detected_at"], e["snapshot_id"], e["prev_snapshot_id"],
          e.get("cinema_id"), e.get("movie_id"), e.get("movie_title"), e.get("date"), e.get("datetime_local"),
          json.dumps(e.get("before"), ensure_ascii=False) if e.get("before") is not None else None,
          json.dumps(e.get("after"), ensure_ascii=False) if e.get("after") is not None else None)
         for e in events],
    )


def save_raw(chain, taken_at, raw):
    """Guarda el crudo comprimido en data/raw/{chain}/{YYYY-MM-DD}/{HHMMSS}Z.json.gz (hora UTC)."""
    ts = datetime.fromisoformat(taken_at)
    folder = config.RAW_DIR / chain / ts.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (ts.strftime("%H%M%S") + "Z.json.gz")
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False)
    return str(path.relative_to(config.ROOT)) if str(path).startswith(str(config.ROOT)) else str(path)
