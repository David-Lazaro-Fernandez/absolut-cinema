"""Pruebas de preventas: títulos de la landing, estrenos del HTML, panel fijo y ritmo de venta."""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import db  # noqa: E402
from analytics import presale as analytics_presale  # noqa: E402
from scraper import presale  # noqa: E402

NOW = datetime.now(timezone.utc)


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")


def test_presale_titles_come_from_the_showtimes_page_of_the_landing():
    landings = [{"slug": "otra", "pages": [{"type": "showtimes", "content": {"movies": [{"id": 1, "name": "No"}]}}]},
                {"slug": "preventas", "pages": [{"type": "html", "content": {}},
                                                {"type": "showtimes", "content": {"movies": [{"id": 72965, "name": " Duna "}]}}]}]
    assert presale.presale_titles(landings) == [{"movie_id": "72965", "title": "Duna"}]
    assert presale.presale_titles([]) == []


def test_release_dates_by_id_and_by_title():
    html = ('<script>var upcoming={"movies":[{"id":1,"movie_id":72965,"name":"Duna: Parte Tres","release_date":"2026-12-17"},'
            '{"id":2,"movie_id":null,"name":"Verity","release_date":"2026-10-01"}]},promos={"a":1};</script>')
    by_id, by_title = presale.release_dates(html)
    assert by_id == {"72965": "2026-12-17"}
    assert by_title["verity"] == "2026-10-01"
    assert presale.release_dates("<html></html>") == ({}, {})


def test_a_title_is_in_presale_until_its_release():
    assert presale.in_presale("2026-10-01", "2026-09-25")
    assert not presale.in_presale("2026-10-01", "2026-10-01")
    assert presale.in_presale(None, "2026-12-31")


def _row(show_id, cinema_id, when, movie_id="m1"):
    return {"show_id": show_id, "cinema_id": cinema_id, "movie_id": movie_id, "datetime_utc": when}


def test_panel_keeps_sampled_shows_and_fills_one_per_cinema():
    rows = [_row("a1", "a", "2026-10-01T10"), _row("a2", "a", "2026-10-01T12"), _row("a3", "a", "2026-10-01T14"),
            _row("b1", "b", "2026-10-01T11"), _row("c1", "c", "2026-10-02T10"), _row("x1", "a", "2026-10-01T10", "m2")]
    picked = [r["show_id"] for r in presale.pick_panel(rows, sampled={"a3"}, per_title=4)]
    assert picked == ["a3", "a1", "b1", "c1", "x1"]      # a3 se conserva; luego una por cine (a, b, c); m2 aparte


def test_ranking_uses_the_latest_reading_and_the_pace_between_two():
    conn = db.register(sqlite3.connect(":memory:"))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE presale_sample (chain, show_id, movie_title, title_norm, cinema_id, release_date,
                    sampled_at, days_to_start, seats, sold)""")
    reads = [("s1", "Duna", "duna", ago(24), 100, 10), ("s1", "Duna", "duna", ago(0), 100, 30),     # +20 en 24 h
             ("s2", "Duna", "duna", ago(0), 100, 50),                                               # sin lectura previa
             ("v1", "Verity", "verity", ago(12), 200, 4), ("v1", "Verity", "verity", ago(0), 200, 6),  # +2 en 12 h
             ("old", "Vieja", "vieja", ago(24 * 5), 100, 90)]                                        # fuera del panel vigente
    conn.executemany("INSERT INTO presale_sample VALUES ('cinemex', ?, ?, ?, 'c1', '2026-12-17', ?, 30, ?, ?)", reads)
    conn.execute("INSERT INTO presale_sample VALUES ('cinepolis', 'p1', 'Duna', 'duna', 'c9', '2026-12-17', ?, 30, 100, 99)", (ago(0),))
    out = {r["title_norm"]: r for r in analytics_presale.presale_ranking(conn)}
    assert set(out) == {"duna", "verity"}
    assert (out["duna"]["shows"], out["duna"]["sold"], out["duna"]["sold_pct"]) == (2, 80, 40.0)
    assert (out["duna"]["paced_shows"], out["duna"]["pace_per_show_day"]) == (1, 20.0)
    assert out["verity"]["pace_per_show_day"] == 4.0
    assert (out["duna"]["pace_pct_day"], out["verity"]["pace_pct_day"]) == (20.0, 2.0)     # puntos del aforo al día
    assert [r["title_norm"] for r in analytics_presale.presale_ranking(conn)] == ["duna", "verity"]


def test_compare_puts_both_chains_on_one_row():
    conn = db.register(sqlite3.connect(":memory:"))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE presale_sample (chain, show_id, movie_title, title_norm, cinema_id, release_date,
                    sampled_at, days_to_start, seats, sold)""")
    conn.executemany("INSERT INTO presale_sample VALUES (?, ?, ?, ?, 'c1', '2026-10-24', ?, 20, 100, ?)",
                     [("cinemex", "a", "BTS Buenos Aires", "bts world tour buenos aires live viewing", ago(0), 40),
                      ("cinepolis", "b", "BTS Buenos Aires: En Vivo", "bts world tour buenos aires en vivo", ago(0), 60),
                      ("cinepolis", "c", "Rammstein", "rammstein live in mexico city", ago(0), 10),
                      ("cinepolis", "d", "Linkin Park", "linkin park unshatter", ago(0), 5)])
    conn.execute("CREATE TABLE current_showtime (chain, title_norm, city_id)")
    conn.execute("INSERT INTO current_showtime VALUES ('cinemex', 'linkin park unshatter', '15')")   # la exhibimos sin preventa
    out = analytics_presale.presale_compare(conn)
    assert [(r["title"], r["sold_pct_cinemex"], r["sold_pct_cinepolis"], r["gap_pp"], r["status"]) for r in out] == [
        ("BTS Buenos Aires", 40.0, 60.0, -20.0, "ambas"), ("Rammstein", None, 10.0, None, "exclusiva_cinepolis"),
        ("Linkin Park", None, 5.0, None, "solo_cinepolis")]
    assert (out[0]["sold_cinemex"], out[0]["seats_cinemex"], out[0]["sold_cinepolis"], out[0]["seats_cinepolis"]) == (40, 100, 60, 100)
