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
    combo = analytics.recommend(conn, *GALERIAS_HMO, adults=3, snacks="combo_2", **WIDE)
    assert {(r["tickets_total"], r["snacks_total"], r["total"]) for r in combo} == {(270.0, 500.0, 770.0)}   # 2 combos para 3
    assert combo[0]["snacks_items"] == [{"name": "Combo Clásico", "units": 2, "price": 250.0}]
    popcorn = analytics.recommend(conn, *GALERIAS_HMO, adults=2, snacks="popcorn", **WIDE)
    assert {r["snacks_total"] for r in popcorn} == {300.0}


def test_without_a_snack_price_the_show_goes_apart(conn):
    first = _first_unpriced(conn, FORUM_TEPIC)
    _price(conn, first, TICKETS["cinemex"])
    assert analytics.recommend(conn, *FORUM_TEPIC, snacks="combo_2", **WIDE) == []      # Cinemex no publica menú en sala
    apart = analytics.recommend(conn, *FORUM_TEPIC, snacks="combo_2", status="snacks_unpriced", **WIDE)
    assert apart and {(r["snacks_total"], r["total"], r["tickets_total"]) for r in apart} == {(None, None, 160.0)}
    summary = analytics.recommend_summary(conn, *FORUM_TEPIC, snacks="combo_2", d0=D0, d1=D1, from_now=False)
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


def test_one_search_gives_what_the_separate_calls_give(conn):
    _price(conn, _first_unpriced(conn, FORUM_TEPIC), TICKETS["cinemex"])
    common = dict(d0=D0, d1=D1, from_now=False, adults=1, children=1, snacks="combo_2")
    found = analytics.recommend_search(conn, *FORUM_TEPIC, per_cinema=2, limit=10_000, **common)
    for status in rec.STATUSES:
        assert found[status] == analytics.recommend(conn, *FORUM_TEPIC, status=status, per_cinema=2, limit=10_000, **common)
    assert found["summary"] == analytics.recommend_summary(conn, *FORUM_TEPIC, **common)
    assert found["titles"] == analytics.recommend_titles(conn, *FORUM_TEPIC, d0=D0, d1=D1, from_now=False)
    title = found["titles"][-1]["title_norm"]
    only = analytics.recommend_search(conn, *FORUM_TEPIC, title_norm=title, **common)
    assert only["titles"] == found["titles"]                                          # el filtro no vacía la lista
    assert {r["title_norm"] for r in only["unpriced"]} <= {title}


def test_a_neutral_tie_keeps_the_order_it_gets():
    base = {"distance_km": 1.0, "total": 100.0, "tickets_total": 100.0, "datetime_local": "2026-09-27T18:00:00", "show_id": "a"}
    tied = [{**base, "chain": "cinepolis"}, {**base, "chain": "cinemex"}]
    for sort in rec.SORTS:
        assert sorted(tied, key=rec._sort_key(sort, favor_us=False))[0]["chain"] == "cinepolis"


def test_each_show_links_to_its_buy_page(conn):
    cinemex = _first_unpriced(conn, FORUM_TEPIC)
    assert cinemex["buy_url"] == f"https://cinemex.com/checkout/{cinemex['show_id']}"
    cinepolis = _first_unpriced(conn, GALERIAS_HMO)
    assert cinepolis["buy_url"] == (f"https://cinepolis.com/mx/horarios?cinema={cinepolis['cinema_id']}"
                                    f"&movie={cinepolis['movie_id']}")


def test_the_cinetecas_link_to_their_sale_or_say_box_office(capture_db):
    conn = capture_db("cineteca_gdl", "cineteca_mty")
    wide = dict(d0="2026-09-30", d1="2026-10-08", from_now=False, radius_km=1.0, limit=1)
    ficg, = analytics.recommend(conn, 20.7366, -103.3811, **wide)
    assert not ficg["box_office_only"]
    assert ficg["buy_url"] == ("https://ticketing.useast.veezi.com/purchase/" + ficg["show_id"].split(":")[1]
                               + "?siteToken=rj5c6tj546eqfqz3qz8raafy3w")
    conarte, = analytics.recommend(conn, 25.6778, -100.2845, **wide)
    assert conarte["box_office_only"] and conarte["buy_url"] is None and conarte["tickets_total"] == 160.0


def test_a_building_is_one_site_with_every_show(conn):
    near = dict(d0=D0, d1=D1, from_now=False, radius_km=0.5)
    by_cinema = {}
    for r in analytics.recommend(conn, *FORUM_TEPIC, status="unpriced", limit=10_000, **near):
        by_cinema.setdefault(r["cinema_id"], r)
    for r in by_cinema.values():
        _price(conn, r, TICKETS["cinemex"])
    found = analytics.recommend_search(conn, *FORUM_TEPIC, per_cinema=1, **near)
    assert len(found["sites"]) == 1
    site = found["sites"][0]
    assert {c["cinema_name"] for c in site["cinemas"]} == {"Forum Tepic", "Forum Tepic Platino"}
    inside = analytics.recommend_search(conn, *FORUM_TEPIC, per_cinema=1, site=(site["lat"], site["lng"]), **near)
    assert len(inside["complete"]) == site["shows"] > len(found["complete"])           # sin tope por cine


MENU = {"Palomitas": 90.0, "Refresco": 60.0, "Combo Clásico": 250.0, "Maxicombo Nachos": 330.0}


def test_the_cheapest_mix_covers_the_whole_group():
    assert rec._snack_plan(MENU, "best", None, 3, 0) == (330.0, [{"name": "Maxicombo Nachos", "units": 1, "price": 330.0}])
    assert rec._snack_plan(MENU, "best", None, 5, 0)[0] == 580.0                     # Maxicombo para 3 + Clásico para 2
    assert rec._snack_plan(MENU, "best", None, 1, 0) == (150.0, [{"name": "Palomitas y refresco", "units": 1, "price": 150.0}])
    assert rec._snack_plan({"Combo Clásico": 250.0}, "best", None, 3, 0) is None       # sin palomitas sueltas, 3 no se cubre
    assert rec._snack_plan({}, "best", None, 2, 0) is None


def test_a_combo_covers_only_who_it_is_for():
    menu = {**MENU, "Combo Junior": 100.0, "Combo Individual Con Cerveza": 120.0}
    assert rec._snack_plan(menu, "best", None, 1, 1)[0] == 220.0                     # Junior para el niño, cerveza para el adulto
    assert rec._snack_plan(menu, "best", None, 0, 2)[0] == 200.0                     # dos Junior
    no_junior = {k: v for k, v in menu.items() if k != "Combo Junior"}
    assert rec._snack_plan(no_junior, "best", None, 0, 2)[0] == 250.0                # la cerveza no cubre a niños
    assert rec._snack_plan(menu, "combo_1", None, 2, 0) is None                      # "cada N" no usa el de cerveza
    assert rec._snack_plan({**menu, "Combo Crepa Individual": 140.0}, "combo_1", None, 2, 0)[0] == 280.0


def test_a_chosen_combo_goes_one_per_its_maximum():
    assert rec._snack_plan(MENU, "none", "Maxicombo Nachos", 5, 0) == (660.0, [{"name": "Maxicombo Nachos", "units": 2, "price": 330.0}])
    assert rec._snack_plan(MENU, "best", "Maxicombo Familiar", 2, 0) is None           # el cine no lo vende
    assert rec._snack_plan(MENU, "combo_3", None, 4, 0)[0] == 660.0                  # un Maxicombo cada tres


def test_every_combo_in_the_table_is_valid():
    assert rec.COMBOS and all(1 <= c["min"] <= c["max"] and c["for"] in {"all", "children", "adults"} for c in rec.COMBOS.values())
    assert {int(k.removeprefix("combo_")) for k in rec.SNACK_PACKAGES if k.startswith("combo_")} <= \
        {n for c in rec.COMBOS.values() if c["for"] == "all" for n in range(c["min"], c["max"] + 1)}


def test_the_options_describe_each_plaza(conn):
    options = analytics.recommend_options(conn, plazas=(None,), d0=D0, d1=D1, from_now=False)
    west, south, east, north = options["plazas"][0]["bbox"]
    assert west < FORUM_TEPIC[1] < east and south < FORUM_TEPIC[0] < north
    assert [d["date"] for d in options["dates"]] == sorted(d["date"] for d in options["dates"])
    assert options["formats"] and options["snacks"] == list(rec.SNACK_PACKAGES)
    assert [c["name"] for c in options["combos"]] == sorted(rec.COMBOS)
    assert {"Forum Tepic", "Forum Tepic Platino"} <= {c["cinema_name"] for c in options["cinemas"]}
    assert analytics.recommend_options(conn, plazas=("gdl",), d0=D0, d1=D1)["plazas"] == []



def test_the_loop_combo_follows_the_day_and_the_cinema_list(conn):
    shows = analytics.recommend(conn, *FORUM_TEPIC, status="unpriced", **WIDE)
    promos = {(r["cinema_id"], r["format_bucket"], datetime.fromisoformat(r["date"]).weekday()): r["promo"]
              for r in shows if r["chain"] == "cinemex"}
    forum = {day: c for (cinema, fmt, day), c in promos.items() if cinema == "156" and fmt == "traditional"}
    assert forum[0]["price"] == forum[2]["price"] == 230.0 and forum[4]["price"] == 365.0       # Forum Tepic en los PDF
    assert forum[0]["name"] == "Combo Lunes" and forum[1]["name"] == "Combo Martes Pareja"
    assert forum[3]["price"] == 255.0 and forum[5] is forum[6] is None
    assert all(c is None or c["name"] == "Martes 2x1" for (_, fmt, _), c in promos.items() if fmt != "traditional")


_MONDAY = {"chain": "cinemex", "cinema_id": "156", "cinema_name": "Forum Tepic", "format_bucket": "traditional",
           "date": "2026-09-28", "movie_id": "1", "distributor": "Warner Bros.", "genre": "Acción", "experience": None,
           "format": "2D", "premium_tier": "traditional", "adult_price": 90.0}
_CINEPOLIS = {**_MONDAY, "chain": "cinepolis", "cinema_id": "x", "week_max_cents": 9200}


def _names(r):
    return [p["name"] for p in rec._promos(r, {})]


def test_no_promo_in_presale_or_special_events():
    assert [p["price"] for p in rec._promos(_MONDAY, {})] == [230.0, 180.0]
    assert rec._promos(_MONDAY, {("cinemex", "1"): "2026-10-01"}) == []                          # antes del estreno
    assert _names({**_MONDAY, "distributor": "Fathom"}) == _names({**_MONDAY, "genre": "Documental|Concierto"}) == []
    assert _names({**_CINEPOLIS, "distributor": "+QueCine"}) == []


def test_the_cinetecas_pay_their_public_fare():
    tuesday = {"chain": "cineteca", "cinema_id": "003", "date": "2026-09-29", "program": "Estrenos"}
    assert rec._public_fare({**tuesday, "date": "2026-10-01"}) == (70.0, 50.0, 50.0)
    assert rec._public_fare(tuesday) == (50.0, 50.0, 50.0)
    assert rec._public_fare({**tuesday, "program": "74 Muestra Internacional de Cine"}) == (70.0, 50.0, 50.0)
    assert rec._public_fare({**tuesday, "program": None}) == (50.0, 50.0, 50.0)
    assert rec._public_fare({**tuesday, "chain": "cineteca_gdl", "cinema_id": "ficg"}) == (60.0, 60.0, 40.0)
    assert rec._public_fare({**tuesday, "chain": "cineteca_gdl", "cinema_id": "cineforo"}) == (50.0, 50.0, 35.0)
    assert rec._public_fare({**tuesday, "chain": "cineteca_mty", "cinema_id": "centro-artes"}) == (80.0, 80.0, 50.0)
    assert rec._public_fare({**tuesday, "chain": "cinemex", "cinema_id": "003"}) is None


def test_cinemex_promos_follow_the_day_and_the_room():
    tuesday, thursday = {**_MONDAY, "date": "2026-09-29"}, {**_MONDAY, "date": "2026-10-01"}
    assert _names(tuesday) == ["Martes 2x1", "Combo Martes Pareja", "Combo Martes Individual"]
    assert [p["people"] for p in rec._promos(tuesday, {})] == [2, 2, 1]
    assert _names({**tuesday, "format_bucket": "premium", "premium_tier": "platinum"}) == ["Martes 2x1"]
    assert _names({**tuesday, "format_bucket": "large", "experience": "imax"}) == []
    assert rec._promos(thursday, {})[0]["price"] == 255.0
    assert rec._promos({**thursday, "cinema_name": "Antara Market"}, {})[0]["price"] == 310.0
    assert _names({**tuesday, "cinema_name": "Antara Market"}) == ["Martes 2x1"]
    assert _names({**_MONDAY, "date": "2026-10-03"}) == []                                          # sábado: nada


def test_cinepolis_promos_follow_the_day_and_the_room():
    monday, tuesday, wednesday = _CINEPOLIS, {**_CINEPOLIS, "date": "2026-09-29"}, {**_CINEPOLIS, "date": "2026-09-30"}

    def promo(r):
        found = rec._promos(r, {})
        return found[0] if found else None
    assert (promo(monday)["price"], promo(monday)["price_max"]) == (245.0, 270.0)
    assert promo({**monday, "experience": "IMAX"})["price"] == 305.0
    assert promo({**monday, "format": "3D"}) is promo({**monday, "premium_tier": "vip"}) is None
    assert promo(tuesday)["price"] == 92.0 and promo({**tuesday, "premium_tier": "vip"})["name"] == "Martes 2x1"
    assert promo({**tuesday, "experience": "SCREENX"}) is promo({**tuesday, "week_max_cents": None}) is None
    assert promo({**wednesday, "format": "3D"})["name"] == "Miércoles 2x1"
    assert promo({**wednesday, "experience": "XE"}) is promo({**wednesday, "premium_tier": "vip"}) is None
    assert promo({**wednesday, "date": "2026-09-16"}) is None                                     # 16 de septiembre
    assert promo({**_CINEPOLIS, "date": "2026-10-01"}) is None                                    # jueves: nada


def _show(tickets, snacks, total, adult=90.0, child=70.0, senior=70.0):
    return {"tickets_total": tickets, "snacks_total": snacks, "snacks_items": [] if snacks is not None else None,
            "total": total, "adult_price": adult, "child_price": child, "senior_price": senior}


def _promo_for(kind, price, price_max=None, people=2, uses=1, pays_one=False):
    return {"kind": kind, "price": price, "price_max": price_max, "people": people, "applied": False,
            "_uses": uses, "_pays_one": pays_one}


def _apply(r, promos, adults, children=0, snacks="best", combo=None, rest=lambda a, k: (0.0, [])):
    return rec._apply_promo(r, promos, adults, children, 0, snacks, combo, rest)


def test_a_combo_covers_two_people_and_prices_their_snacks():
    r, promo = _show(180.0, None, None), _promo_for("combo", 230.0)          # Cinemex: sin precio de dulcería
    assert _apply(r, [promo], 2, rest=lambda a, k: None) is promo
    assert promo["applied"] and (r["tickets_total"], r["snacks_total"], r["total"]) == (230.0, 0.0, 230.0)
    r, promo = _show(372.0, None, None, adult=116.0), _promo_for("combo", 230.0)   # 2 adultos y 2 niños (Tezontle)
    _apply(r, [promo], 2, 2, rest=lambda a, k: None)
    assert promo["applied"] and (r["tickets_total"], r["total"]) == (370.0, None)       # el resto, sin precio de dulcería
    r, promo = _show(320.0, None, None), _promo_for("combo", 230.0)                    # con boletos a 90 sale más caro
    _apply(r, [promo], 2, 2, rest=lambda a, k: None)
    assert not promo["applied"] and r["tickets_total"] == 320.0


def test_the_combo_range_counts_its_high_price():
    r, promo = _show(180.0, 150.0, 330.0), _promo_for("combo", 245.0, 270.0)
    _apply(r, [promo], 2)
    assert promo["applied"] and r["total"] == 270.0
    r, promo = _show(180.0, 80.0, 260.0), _promo_for("combo", 245.0, 270.0)  # más caro que sin promoción
    _apply(r, [promo], 2)
    assert not promo["applied"] and r["total"] == 260.0


def test_a_two_for_one_replaces_the_pairs_that_save_the_most():
    r, promo = _show(340.0, 0.0, 340.0), _promo_for("2x1", 100.0)            # Cinépolis: 3 adultos a 90 y 1 niño a 70
    _apply(r, [promo], 3, 1, snacks="none")
    assert promo["applied"] and r["total"] == 340.0 - 180.0 + 100.0
    r, promo = _show(460.0, 0.0, 460.0), _promo_for("2x1", 90.0, uses=3, pays_one=True)   # Loop: 4 adultos y 2 niños
    _apply(r, [promo], 4, 2, snacks="none")
    assert r["total"] == 460.0 - 90.0 - 90.0 - 70.0


def test_the_group_uses_the_cheapest_promo_of_the_day():
    two_for_one = _promo_for("2x1", 90.0, uses=3, pays_one=True)
    pair, solo = _promo_for("combo", 340.0), _promo_for("combo", 240.0, people=1)
    r = _show(180.0, None, None)                                              # pareja con dulcería en Cinemex
    assert _apply(r, [two_for_one, pair, solo], 2, rest=lambda a, k: None) is pair and r["total"] == 340.0
    r = _show(90.0, None, None)                                               # una persona
    assert _apply(r, [two_for_one, pair, solo], 1, rest=lambda a, k: None) is solo and r["total"] == 240.0
    r = _show(180.0, 0.0, 180.0)                                              # pareja sin dulcería
    assert _apply(r, [two_for_one, pair, solo], 2, snacks="none") is two_for_one and r["total"] == 90.0


def test_no_combo_for_a_chosen_menu_combo():
    r, promo = _show(180.0, 0.0, 180.0), _promo_for("combo", 50.0)
    assert _apply(r, [promo], 2, snacks="none", combo="Combo Nachos") is promo and not promo["applied"]
