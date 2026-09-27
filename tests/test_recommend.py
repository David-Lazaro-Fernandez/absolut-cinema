"""El recomendador (`analytics/recommender.py`) sobre la captura grabada: boletos por tipo (adulto, niño, adulto mayor)
de la lectura de precio de cada cine, formato y día; dulcería con el menú en sala de Cinépolis; presupuesto sobre el
total; radio; funciones sin precio de dulcería o de boletos aparte; tope por cine y desempate a favor de Cinemex.
Puntos de partida: Forum Tepic (Cinemex, con su Platino en el mismo edificio y Tepic a ~2 km) y Galerías Mall
Hermosillo (Cinépolis, con su VIP)."""
import json
from datetime import datetime, timezone

import pytest

import analytics
from analytics import recommender as rec

FORUM_TEPIC = (21.493764, -104.8664)
GALERIAS_HMO = (29.068, -110.957)
D0, D1 = "2026-09-25", "2026-10-07"
WIDE = dict(d0=D0, d1=D1, from_now=False, radius_km=5.0, limit=10_000)
TICKETS = {"cinemex": [("ADULTO", 8000), ("MENOR", 6000), ("MAYOR 60", 5000)],
           "cinepolis": [("Admisión General", 9000), ("Niños", 7000), ("3 Era Edad", 6500), ("Que Oferton 2026", 3500)]}


@pytest.fixture
def conn(capture_db):
    return capture_db("cinemex", "cinepolis", "cineteca")


def _price(conn, row, tickets):
    conn.execute("""INSERT INTO price_sample (chain, show_id, cinema_id, format_bucket, day_type, sampled_at, general_cents, tickets_json)
                    VALUES (?, 'x', ?, ?, ?, ?, ?, ?)""",
                 (row["chain"], row["cinema_id"], row["format_bucket"], row["day_type"], datetime.now(timezone.utc).isoformat(),
                  tickets[0][1], json.dumps([{"name": n, "cents": c} for n, c in tickets])))


def _menu(conn, cinema_id, prices):
    sampled_at = datetime.now(timezone.utc).isoformat()      # una lectura del menú: todos sus productos a la misma hora
    for product, cents in prices.items():
        conn.execute("""INSERT INTO concession_price (chain, cinema_id, sampled_at, category, product_id, product_name, price_cents)
                        VALUES ('cinepolis', ?, ?, 'Clásicos', ?, ?, ?)""", (cinema_id, sampled_at, product, product, cents))


def _first_unpriced(conn, start):
    return analytics.recommend(conn, *start, status="unpriced", **WIDE)[0]


def test_each_person_pays_their_own_ticket(conn):
    first = _first_unpriced(conn, FORUM_TEPIC)
    assert analytics.recommend(conn, *FORUM_TEPIC, **WIDE) == []                      # sin lecturas no hay precio
    _price(conn, first, TICKETS["cinemex"])
    priced = analytics.recommend(conn, *FORUM_TEPIC, adults=2, children=1, seniors=1, **WIDE)
    assert {(r["cinema_id"], r["format_bucket"], r["day_type"]) for r in priced} == \
        {(first["cinema_id"], first["format_bucket"], first["day_type"])}
    r = priced[0]
    assert (r["adult_price"], r["child_price"], r["senior_price"]) == (80.0, 60.0, 50.0)
    assert r["tickets_total"] == r["total"] == 270.0 and r["snacks_total"] == 0.0 and r["status"] == "complete"


def test_a_promotion_is_not_taken_for_a_child_ticket():
    general, child, senior = rec._ticket_prices(json.dumps([{"name": n, "cents": c} for n, c in TICKETS["cinepolis"]]), 9000)
    assert (general, child, senior) == (90.0, 70.0, 65.0)
    assert rec._ticket_prices(json.dumps([{"name": "ADULTO", "cents": 8000}]), 8000) == (80.0, 80.0, 80.0)   # sin boleto de niño


def test_snacks_come_from_the_menu_of_each_cinepolis(conn):
    first = _first_unpriced(conn, GALERIAS_HMO)
    _price(conn, first, TICKETS["cinepolis"])
    _menu(conn, first["cinema_id"], {"Palomitas": 9000, "Refresco": 6000, "Combo Clásico": 25000})
    combo = analytics.recommend(conn, *GALERIAS_HMO, adults=3, snacks="combo", **WIDE)
    assert {(r["tickets_total"], r["snacks_total"], r["total"]) for r in combo} == {(270.0, 500.0, 770.0)}   # 2 combos para 3
    popcorn = analytics.recommend(conn, *GALERIAS_HMO, adults=2, snacks="popcorn", **WIDE)
    assert {r["snacks_total"] for r in popcorn} == {300.0}


def test_without_a_snack_price_the_show_goes_apart(conn):
    first = _first_unpriced(conn, FORUM_TEPIC)
    _price(conn, first, TICKETS["cinemex"])
    assert analytics.recommend(conn, *FORUM_TEPIC, snacks="combo", **WIDE) == []      # Cinemex no publica menú en sala
    apart = analytics.recommend(conn, *FORUM_TEPIC, snacks="combo", status="snacks_unpriced", **WIDE)
    assert apart and {(r["snacks_total"], r["total"], r["tickets_total"]) for r in apart} == {(None, None, 160.0)}
    summary = analytics.recommend_summary(conn, *FORUM_TEPIC, snacks="combo", d0=D0, d1=D1, from_now=False)
    assert summary["shows"] == 0 and summary["snacks_unpriced"] == len(apart) and summary["cheapest"] is None


def test_the_budget_counts_the_whole_group(conn):
    first = _first_unpriced(conn, FORUM_TEPIC)
    _price(conn, first, TICKETS["cinemex"])
    assert analytics.recommend(conn, *FORUM_TEPIC, adults=1, children=1, budget=140, **WIDE)
    assert analytics.recommend(conn, *FORUM_TEPIC, adults=1, children=1, budget=139, **WIDE) == []
    summary = analytics.recommend_summary(conn, *FORUM_TEPIC, adults=1, children=1, budget=140, d0=D0, d1=D1, from_now=False)
    assert summary["cheapest"]["total"] == 140.0 and summary["saving"] == 0.0


def test_the_radius_is_a_straight_line_from_the_start(conn):
    near = {r["cinema_name"] for r in analytics.recommend(conn, *FORUM_TEPIC, status="unpriced", **{**WIDE, "radius_km": 0.5})}
    assert near == {"Forum Tepic", "Forum Tepic Platino"}
    wide = analytics.recommend(conn, *FORUM_TEPIC, status="unpriced", **WIDE)
    assert "Tepic" in {r["cinema_name"] for r in wide} and all(r["distance_km"] <= 5 for r in wide)


def test_per_cinema_caps_each_cinema(conn):
    counts = {}
    for r in analytics.recommend(conn, *FORUM_TEPIC, status="unpriced", per_cinema=2, **WIDE):
        counts[r["cinema_id"]] = counts.get(r["cinema_id"], 0) + 1
    assert set(counts.values()) == {2} and len(counts) == 3


def test_titles_near_the_start(conn):
    titles = analytics.recommend_titles(conn, *FORUM_TEPIC, d0=D0, d1=D1, from_now=False)
    assert titles == sorted(titles, key=lambda t: (-t["shows"], t["title_norm"]))
    only = analytics.recommend(conn, *FORUM_TEPIC, status="unpriced", title_norm=titles[0]["title_norm"], **WIDE)
    assert only and {r["title_norm"] for r in only} == {titles[0]["title_norm"]}


def test_a_tie_goes_to_cinemex():
    base = {"distance_km": 1.0, "total": 100.0, "tickets_total": 100.0, "datetime_local": "2026-09-27T18:00:00"}
    tied = [{**base, "chain": "cinepolis", "show_id": "a"}, {**base, "chain": "cinemex", "show_id": "b"}]
    for sort in rec.SORTS:
        assert sorted(tied, key=rec._sort_key(sort))[0]["chain"] == "cinemex"


def test_without_a_package_cinepolis_still_shows_its_snack_reference(conn):
    first = _first_unpriced(conn, GALERIAS_HMO)
    _price(conn, first, TICKETS["cinepolis"])
    _menu(conn, first["cinema_id"], {"Palomitas": 9000, "Refresco": 6000})
    rows = analytics.recommend(conn, *GALERIAS_HMO, **WIDE)
    assert rows and {(r["snacks_total"], r["snack_reference"]) for r in rows} == {(0.0, 150.0)}


def test_the_public_catalog_carries_the_same_prices(conn):
    from scripts import export_recommender as export

    first = _first_unpriced(conn, GALERIAS_HMO)
    _price(conn, first, TICKETS["cinepolis"])
    _menu(conn, first["cinema_id"], {"Palomitas": 9000, "Refresco": 6000, "Combo Clásico": 25000})
    catalog = analytics.recommend_catalog(conn, D0, D1, from_now=False, plaza=None)
    price = next(p for p in catalog["prices"] if p["cinema_id"] == first["cinema_id"])
    assert (price["adult"], price["child"], price["senior"]) == (90.0, 70.0, 65.0)
    cinema = next(c for c in catalog["cinemas"] if c["cinema_id"] == first["cinema_id"])
    assert cinema["snacks"] == {"Palomitas": 90.0, "Refresco": 60.0, "Combo Clásico": 250.0}
    data = export.compact(export.merge({"nacional": catalog}), [export.area("nacional", catalog["cinemas"])])
    assert sum(len(s[-1]) for s in data["shows"]) == len(catalog["shows"])
    west, south, east, north = data["plazas"][0][4]
    assert west < cinema["lng"] < east and south < cinema["lat"] < north
    ix = [c[1] for c in data["cinemas"]].index(cinema["cinema_name"])
    key = f"{ix}|{data['formats'].index(first['format_bucket'])}|{first['day_type']}"
    assert data["prices"][key][:3] == [90.0, 70.0, 65.0]
