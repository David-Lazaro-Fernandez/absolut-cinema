"""Plazas: membresía compartida (scraper/plazas.py) y su traducción a SQL en analytics, sobre una base en memoria."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import plaza as aplazas  # noqa: E402
from analytics import queries  # noqa: E402
from scraper import plazas, store  # noqa: E402


def test_membership_is_per_chain_and_union_is_stable():
    assert plazas.city_ids("cdmx", "cinepolis") == ("cdmx",)
    assert plazas.city_ids("cdmx", "cinemex") == ("15", "16", "17", "18", "19", "20")
    assert plazas.city_ids("nada", "cinemex") == ()
    assert plazas.city_ids_for(("cdmx", "gdl", "cdmx"), "cinepolis") == ("cdmx", "guadalajara", "tlajomulco")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(store.SCHEMA)
    store.upsert_cinemas(c, [
        {"chain": "cinepolis", "cinema_id": "cinepolis-universidad-cdmx", "name": "Universidad", "city_id": "cdmx"},
        {"chain": "cinepolis", "cinema_id": "cinepolis-carrousel-tijuana", "name": "Carrousel", "city_id": "tijuana"},
        {"chain": "cinemex", "cinema_id": "26", "name": "Centro Telmex", "city_id": "15", "state_id": "8"},
        {"chain": "cinemex", "cinema_id": "300", "name": "Guadalajara", "city_id": "35", "state_id": "14"},
    ], "2026-09-11T20:00:00+00:00")
    for chain, cid, city, i in (("cinepolis", "cinepolis-universidad-cdmx", "cdmx", 1), ("cinepolis", "cinepolis-carrousel-tijuana", "tijuana", 2),
                                ("cinemex", "26", "15", 3), ("cinemex", "300", "35", 4)):
        c.execute("INSERT INTO current_showtime (chain, show_id, snapshot_id, first_seen, cinema_id, city_id, date, datetime_local, datetime_utc) "
                  "VALUES (?, ?, 1, 't', ?, ?, '2026-09-11', '2026-09-11T20:00:00', '2036-01-01T00:00:00+00:00')", (chain, f"s{i}", cid, city))
        c.execute("INSERT INTO auditorium (chain, cinema_id, screen, seats) VALUES (?, ?, '1', 100)", (chain, cid))
    yield c
    c.close()


def test_plaza_where_filters_rows_and_national_keeps_the_compared_chains(conn):
    where, params = aplazas.plaza_where("cdmx")
    got = {r[0] for r in conn.execute(f"SELECT cinema_id FROM current_showtime WHERE 1 = 1{where}", params)}
    assert got == {"cinepolis-universidad-cdmx", "26"}
    assert aplazas.plaza_where(None) == (" AND chain IN (?,?)", ["cinemex", "cinepolis"])   # nacional: las dos comparables
    with pytest.raises(ValueError):
        aplazas.plaza_where("marte")


def test_plaza_cinema_where_goes_through_the_cinema_dimension(conn):
    where, params = aplazas.plaza_cinema_where("gdl", "a.")
    got = [r[0] for r in conn.execute(f"SELECT a.cinema_id FROM auditorium a WHERE 1 = 1{where}", params)]
    assert got == ["300"]


def test_plazas_lists_only_those_with_cinemas(conn):
    assert aplazas.plazas(conn) == [{"plaza": "cdmx", "cinemas_cinemex": 1, "cinemas_cinepolis": 1},
                                    {"plaza": "gdl", "cinemas_cinemex": 1, "cinemas_cinepolis": 0}]


def test_plaza_coverage_maps_raw_geography_to_plaza(conn):
    cov = {(r["chain"], r["city_id"]): r for r in aplazas.plaza_coverage(conn)}
    assert cov[("cinepolis", "tijuana")]["plaza"] is None and cov[("cinepolis", "tijuana")]["shows"] == 1
    assert cov[("cinemex", "15")]["plaza"] == "cdmx" and cov[("cinemex", "15")]["state_id"] == "8"


def test_window_with_plaza_and_utc_cutoff(conn):
    rows = queries.kpis(conn, "2026-09-11", "2026-09-11", plaza="cdmx")
    assert {(r["chain"], r["cinemas"]) for r in rows} == {("cinepolis", 1), ("cinemex", 1)}
    assert sum(r["shows"] for r in queries.kpis(conn, "2026-09-11", "2026-09-11")) == 4
    where, params, _ = queries._window("2000-01-01", "2000-01-01", plaza="gdl", alias="s.")
    assert where.startswith("s.date BETWEEN ? AND ? AND (") and params[2:] == ["cinemex", "35", "38", "cinepolis", "guadalajara", "tlajomulco"]
