"""Bases en memoria cargadas con la captura grabada de cada cadena (`scripts/capture_fixtures.py`), para probar
`analytics/` con dato real sin red ni `data/snapshots.db`."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import db  # noqa: E402
from scraper import config, run, store  # noqa: E402
from scripts import capture_fixtures as fixtures  # noqa: E402


@pytest.fixture
def capture_db(tmp_path, monkeypatch):
    """Fábrica: `capture_db("cinemex", "cineteca")` devuelve una conexión con la captura grabada de esas cadenas escrita
    por `run.commit`, con `title_key` registrada como la registra `analytics.connect()`."""
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)      # run.commit registra en run.log: fuera del log real
    opened = []

    def make(*chains):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(store.SCHEMA)
        for chain in chains:
            taken_at = fixtures.load(chain, "responses")["recorded_at"]
            raw = fixtures.replay(chain)
            assert run.commit(conn, chain, store.begin_snapshot(conn, chain, taken_at), taken_at, raw, 0, save_raw=False)
        opened.append(conn)
        return db.register(conn)

    yield make
    for conn in opened:
        conn.close()
