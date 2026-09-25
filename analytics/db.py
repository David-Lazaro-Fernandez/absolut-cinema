"""Conexión de solo lectura a la base del scraper, con `title_key` disponible en SQL."""
import sqlite3
from pathlib import Path

from scraper import config, normalize, titles


def connect(path=None):
    """Abre snapshots.db en modo lectura. El scraper escribe en WAL, así que leer mientras
    corre un snapshot no bloquea a ninguno de los dos."""
    db = Path(path) if path else config.DB_PATH
    if not db.exists():
        raise FileNotFoundError(f"No existe {db}; corre primero `python3 -m scraper.run`.")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return register(conn)


def register(conn):
    """Registra en la conexión las funciones SQL de `analytics/`: `title_key(title_norm)`, la llave de título común a
    ambas cadenas (`scraper/titles.py`), por la que agrupan las consultas que comparan películas entre cadenas, y
    `norm_title(texto)`, para las búsquedas del explorador sin mayúsculas ni acentos."""
    conn.create_function("title_key", 1, titles.title_key, deterministic=True)
    conn.create_function("norm_title", 1, normalize.norm_title, deterministic=True)
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
