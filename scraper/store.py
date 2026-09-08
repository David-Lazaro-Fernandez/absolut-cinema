"""Persistencia en SQLite: metadatos de snapshots, estado actual por cadena y eventos de cambio."""
import gzip
import json
import sqlite3
from datetime import datetime

from . import config
from .normalize import COLUMNS

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
  error TEXT
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
  kind TEXT NOT NULL,          -- added | removed | moved | changed | availability
  detected_at TEXT NOT NULL,
  snapshot_id INTEGER NOT NULL,
  prev_snapshot_id INTEGER,
  cinema_id TEXT, movie_id TEXT, movie_title TEXT, date TEXT, datetime_local TEXT,
  before_json TEXT,
  after_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_detected ON event (chain, detected_at);
CREATE INDEX IF NOT EXISTS idx_event_show ON event (chain, show_id);
CREATE INDEX IF NOT EXISTS idx_current_cinema ON current_showtime (chain, cinema_id, date);
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
""" % ",\n  ".join(f"{c} TEXT" if c not in ("lat", "lng", "duration_min") else f"{c} REAL" for c in COLUMNS if c not in ("chain", "show_id"))

ROW_COLUMNS = [c for c in COLUMNS if c not in ("chain", "show_id")]


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
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


def replace_current(conn, chain, snapshot_id, rows, previous, taken_at):
    conn.execute("DELETE FROM current_showtime WHERE chain = ?", (chain,))
    cols = ["chain", "show_id", "snapshot_id", "first_seen"] + ROW_COLUMNS
    placeholders = ", ".join("?" for _ in cols)
    data = []
    for r in rows:
        prev = previous.get(r["show_id"])
        first_seen = prev["first_seen"] if prev and prev.get("first_seen") else taken_at
        data.append([chain, r["show_id"], snapshot_id, first_seen] + [r.get(c) for c in ROW_COLUMNS])
    conn.executemany(f"INSERT INTO current_showtime ({', '.join(cols)}) VALUES ({placeholders})", data)


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
