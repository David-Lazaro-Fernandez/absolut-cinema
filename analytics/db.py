"""Conexión de solo lectura a la base del scraper."""
import sqlite3
from pathlib import Path

from scraper import config


def connect(path=None):
    """Abre snapshots.db en modo lectura. El scraper escribe en WAL, así que leer mientras
    corre un snapshot no bloquea a ninguno de los dos."""
    db = Path(path) if path else config.DB_PATH
    if not db.exists():
        raise FileNotFoundError(f"No existe {db}; corre primero `python3 -m scraper.run`.")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
