"""La oferta independiente (`analytics/independents.py`) sobre la captura grabada de la Cineteca y de Cinemex: shares de
cada cadena que suman 100, el solape por llave de título (la regla DOB/SUB) y la ocupación desde los planos. El hallazgo
de Capa 1 solo se enciende con la lectura del plano confirmada y si un título cruza el umbral."""
import sys
from datetime import datetime, timedelta, timezone

import pytest

import analytics
from analytics import independents

findings_module = sys.modules["analytics.findings"]      # `analytics.findings` es la función
D0 = D1 = "2026-09-27"                                  # el día grabado de la Cineteca


@pytest.fixture
def conn(capture_db):
    c = capture_db("cinemex", "cineteca")
    # Los cines grabados de Cinemex están en Sonora: se mudan a CDMX y uno exhibe "Cars" el mismo día que la Cineteca.
    c.execute("UPDATE current_showtime SET city_id = '15', date = ?, datetime_local = ? || substr(datetime_local, 11), "
              "datetime_utc = ? || substr(datetime_utc, 11) WHERE chain = 'cinemex'", (D0, D0, D0))
    c.execute("UPDATE cinema SET city_id = '15' WHERE chain = 'cinemex'")
    c.execute("UPDATE current_showtime SET movie_title = 'Cars', title_norm = 'cars' "
              "WHERE chain = 'cinemex' AND show_id = (SELECT MIN(show_id) FROM current_showtime WHERE chain = 'cinemex')")
    now = datetime.now(timezone.utc)
    for i, (cinema_id, title, sold, hour) in enumerate([("001", "Cocodrilos", 90, 18), ("001", "Cocodrilos", 80, 19),
                                                         ("002", "Moscas", 30, 13), ("003", "Cars 20 aniversario DOB", 50, 16)] * 3):
        c.execute("""INSERT INTO occupancy_sample (chain, show_id, cinema_id, screen, movie_title, datetime_local, sampled_at,
                                                   minutes_to_start, seats, sold, broken, sold_pct)
                     VALUES ('cineteca', ?, ?, 'Sala 1', ?, ?, ?, -20, 100, ?, 0, ?)""",
                  (f"{cinema_id}:{i}", cinema_id, title, f"{D0}T{hour:02d}:00:00", (now - timedelta(hours=i)).isoformat(), sold, sold))
    return c


def test_shares_sum_to_100_per_chain(conn):
    venues = analytics.independent_summary(conn, D0, D1, from_now=False)
    assert [v["cinema_id"] for v in venues] == ["002", "003", "001"]
    assert sum(v["share_shows"] for v in venues) == pytest.approx(100, abs=0.2)
    titles = analytics.independent_titles(conn, D0, D1, from_now=False, limit=1000)
    assert sum(t["share_shows"] for t in titles) == pytest.approx(100, abs=0.5)
    assert all(t["subtitled"] + t["spanish"] + t["other"] == t["shows"] for t in titles)
    slots = analytics.independent_slots(conn, D0, D1, from_now=False)
    assert [r["chain"] for r in slots] == ["cinemex"] * 6 + ["cineteca"] * 6
    for chain in ("cinemex", "cineteca"):
        assert sum(r["share"] for r in slots if r["chain"] == chain) == pytest.approx(100, abs=0.5)


def test_versions_group_by_title_and_match_ours(conn):
    titles = {t["title_norm"]: t for t in analytics.independent_titles(conn, D0, D1, from_now=False, limit=1000)}
    assert titles["mary y max"]["title"] == "Mary y Max"            # DOB y SUB, una sola película
    assert titles["mary y max"]["subtitled"] and titles["mary y max"]["spanish"]
    overlap = {r["title_norm"]: r for r in analytics.independent_overlap(conn, D0, D1, from_now=False)}
    assert overlap["cars"]["status"] == "shared" and overlap["cars"]["shows_vs"] == 1
    assert overlap["cars"]["title"] == "Cars 20 aniversario"
    assert overlap["mary y max"]["status"] == "indep_only"
    assert overlap["cocodrilos"]["samples"] == 6 and overlap["cocodrilos"]["sold_pct"] == 85.0
    assert overlap["mary y max"]["sold_pct"] is None


def test_the_order_is_deterministic(conn):
    for fn in (analytics.independent_summary, analytics.independent_titles, analytics.independent_overlap, analytics.independent_slots):
        first = fn(conn, D0, D1, from_now=False)
        assert fn(conn, D0, D1, from_now=False) == first
    overlap = analytics.independent_overlap(conn, D0, D1, from_now=False)
    assert overlap == sorted(overlap, key=lambda r: (-r["shows_indep"], r["title_norm"]))


def test_occupancy_by_cinema_weights_by_seats_in_day_order(conn):
    occ = analytics.occupancy_by_cinema(conn)
    assert [(r["cinema_id"], r["slot"], r["sold_pct"]) for r in occ] == [
        ("001", "de_18_a_21", 85.0), ("002", "de_12_a_15", 30.0), ("003", "de_15_a_18", 50.0)]


def test_the_finding_waits_for_a_confirmed_seat_map(conn, monkeypatch):
    assert findings_module._independent_finding(conn, D0, D1, plaza="cdmx") is None
    monkeypatch.setattr(findings_module, "OCCUPANCY_CONFIRMED", True)
    found = findings_module._independent_finding(conn, D0, D1, plaza="cdmx")
    assert found["topic"] == "independientes" and found["title"].startswith("Cocodrilos llena 85 %")
    assert findings_module._independent_finding(conn, D0, D1, plaza="gdl") is None
    monkeypatch.setattr(findings_module, "INDEP_MIN_SOLD_PCT", 90.0)
    assert findings_module._independent_finding(conn, D0, D1, plaza="cdmx") is None


def test_conclusions_leave_out_what_has_no_data(conn, monkeypatch):
    out = analytics.independent_conclusions(conn, D0, D1)
    assert set(out) == {"programa", "solape", "franjas"}              # sin planos confirmados, sin ocupación
    monkeypatch.setattr(findings_module, "OCCUPANCY_CONFIRMED", True)
    assert "ocupacion" in analytics.independent_conclusions(conn, D0, D1)
    assert independents.OCCUPANCY_CONFIRMED is False
