"""Conjuntos del explorador (`analytics/datasets.py`) sobre SQLite: filtros opcionales, búsqueda sin acentos y
funciones de la semana (publicadas y cerradas)."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import datasets, db  # noqa: E402


def test_where_skips_empty_and_expands_lists():
    assert datasets.where([("a = ?", None), ("b = ?", ""), ("c IN ({marks})", ())]) == ("", [])
    sql, params = datasets.where([("a = ?", 1), ("c IN ({marks})", ("x", "y"))], prefix="AND")
    assert sql == " AND a = ? AND c IN (?,?)" and params == [1, "x", "y"]


def test_contains_ignores_accents_and_case():
    assert datasets.contains("  Película ") == "%pelicula%"
    assert datasets.contains("") is None


def test_week_showtimes_joins_open_and_closed():
    conn = db.register(sqlite3.connect(":memory:"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE cinema (chain, cinema_id, name)")
    conn.execute("INSERT INTO cinema VALUES ('cinemex', 'c1', 'Pedregal')")
    conn.execute("""CREATE TABLE current_showtime (chain, show_id, cinema_id, movie_title, date, datetime_local, screen,
                    language, format, experience, premium_tier, availability, first_seen)""")
    conn.execute("""INSERT INTO current_showtime VALUES ('cinemex', 's1', 'c1', 'La Película', '2026-10-01',
                    '2026-10-01T18:00:00', '1', 'spanish', '2D', NULL, 'traditional', 'high', '2026-09-25T00:00:00+00:00')""")
    conn.execute("""CREATE TABLE event (chain, show_id, kind, detected_at, cinema_id, movie_title, date, before_json)""")
    conn.execute("INSERT INTO event VALUES ('cinemex', 's0', 'removed', '2026-09-30T10:00:00+00:00', 'c1', 'Otra', '2026-10-01', ?)",
                 (json.dumps({"datetime_local": "2026-10-01T12:00:00", "screen": "2"}),))
    both = datasets.week_showtimes(conn, "2026-10-01", "2026-10-01")
    assert [(r["show_id"], r["closed_kind"]) for r in both] == [("s0", "removed"), ("s1", None)]
    assert [r["show_id"] for r in datasets.week_showtimes(conn, "2026-10-01", "2026-10-01", only_open=True)] == ["s1"]
    assert [r["show_id"] for r in datasets.week_showtimes(conn, "2026-10-01", "2026-10-01", search="pelicula")] == ["s1"]
