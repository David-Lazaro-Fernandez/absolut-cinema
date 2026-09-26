"""El mapa de cines (`analytics/cinema_locations.py`) sobre la captura grabada de las tres cadenas más muestreos sintéticos:
una fila por cine con coordenadas, el boleto más reciente sin eventos, la ocupación solo con planos suficientes y el
destacado de cada cadena."""
from datetime import datetime, timedelta, timezone

import pytest

import analytics
from analytics import cinema_locations

CMX, CNP = "cinemex", "cinepolis"


@pytest.fixture
def conn(capture_db):
    c = capture_db(CMX, CNP, "cineteca")
    cmx = [r[0] for r in c.execute("SELECT cinema_id FROM cinema WHERE chain = ? ORDER BY cinema_id", (CMX,))]
    cnp = [r[0] for r in c.execute("SELECT cinema_id FROM cinema WHERE chain = ? ORDER BY cinema_id", (CNP,))]
    now = datetime.now(timezone.utc)

    def price(chain, cinema_id, cents, days_ago, name="General"):
        c.execute("""INSERT INTO price_sample (chain, show_id, cinema_id, format_bucket, day_type, sampled_at, general_cents, tickets_json)
                     VALUES (?, 'x', ?, 'traditional', 'weekend', ?, ?, ?)""",
                  (chain, cinema_id, (now - timedelta(days=days_ago)).isoformat(), cents, f'[{{"name": "{name}"}}]'))

    price(CMX, cmx[0], 9000, 10); price(CMX, cmx[0], 8000, 1)             # gana la lectura más reciente
    price(CMX, cmx[1], 7000, 2)
    price(CNP, cnp[0], 1500, 0, name="Evento Matinee")                        # los eventos no cuentan
    price(CNP, cnp[0], 9500, 3)
    c.execute("INSERT INTO auditorium (chain, cinema_id, screen, seats) VALUES (?, ?, '1', 100), (?, ?, '2', 150)", (CMX, cmx[0], CMX, cmx[0]))
    for i in range(cinema_locations.OCCUPANCY_MIN_SAMPLES):
        c.execute("""INSERT INTO occupancy_sample (chain, show_id, cinema_id, sampled_at, minutes_to_start, seats, sold)
                     VALUES (?, ?, ?, ?, -20, 100, 40)""", (CNP, f"s{i}", cnp[1], now.isoformat()))
    c.execute("""INSERT INTO occupancy_sample (chain, show_id, cinema_id, sampled_at, minutes_to_start, seats, sold)
                 VALUES (?, 'solo', ?, ?, -20, 100, 90)""", (CNP, cnp[2], now.isoformat()))       # una sola: no alcanza
    return c, {CMX: cmx, CNP: cnp}


def test_one_row_per_cinema_with_what_we_know(conn):
    conn, ids = conn
    data = {(r["chain"], r["cinema_id"]): r for r in analytics.cinema_map(conn, "2026-09-25", "2026-10-07", from_now=False)}
    assert len(data) == conn.execute("SELECT COUNT(*) FROM cinema WHERE lat IS NOT NULL").fetchone()[0]
    first_cmx, first_cnp = data[(CMX, ids[CMX][0])], data[(CNP, ids[CNP][0])]
    assert first_cmx["ticket_price"] == 80.0 and first_cmx["screens"] == 2 and first_cmx["seats"] == 250
    assert first_cmx["shows"] > 0 and first_cmx["sold_pct"] is None
    assert first_cnp["ticket_price"] == 95.0
    assert (first_cmx["ticket_max"], first_cmx["ticket_max_format"]) == (80.0, "traditional")   # la lectura vieja de 90 no cuenta
    assert first_cnp["ticket_max"] == 95.0                                   # el evento de $15 tampoco
    assert data[(CNP, ids[CNP][1])]["sold_pct"] == 40.0
    assert data[(CNP, ids[CNP][2])]["sold_pct"] is None


def test_highlights_pick_the_best_cinema_of_each_chain(conn):
    conn, ids = conn
    hl = {(h["metric"], h["chain"]): h for h in analytics.cinema_highlights(conn, "2026-09-25", "2026-10-07", from_now=False)}
    assert hl[("ticket_price", CMX)]["cinema_id"] == ids[CMX][1] and hl[("ticket_price", CMX)]["cinemas"] == 2
    assert hl[("sold_pct", CNP)]["value"] == 40.0
    assert ("sold_pct", CMX) not in hl                                        # sin dato, sin destacado
    order = [h["metric"] for h in analytics.cinema_highlights(conn, "2026-09-25", "2026-10-07", from_now=False)]
    assert order == sorted(order, key=list(cinema_locations.HIGHLIGHTS).index)


def test_the_plaza_filters_the_map(conn):
    conn, _ = conn
    assert analytics.cinema_map(conn, "2026-09-25", "2026-10-07", from_now=False, plaza="gdl") == []
    cdmx = analytics.cinema_map(conn, "2026-09-25", "2026-10-07", from_now=False, plaza="cdmx")
    assert {r["chain"] for r in cdmx} == {"cineteca"}                         # los cines grabados de las cadenas están en Sonora


def test_cinema_ids_narrow_the_map_and_the_highlights(conn):
    conn, ids = conn
    picked = (ids[CMX][1], ids[CNP][0])
    data = analytics.cinema_map(conn, "2026-09-25", "2026-10-07", from_now=False, cinema_ids=picked)
    assert {r["cinema_id"] for r in data} == set(picked)
    hl = {(h["metric"], h["chain"]): h for h in
          analytics.cinema_highlights(conn, "2026-09-25", "2026-10-07", from_now=False, cinema_ids=picked)}
    assert hl[("ticket_price", CMX)]["cinemas"] == 1 and hl[("ticket_price", CNP)]["cinema_id"] == ids[CNP][0]


def test_cinemas_in_the_same_building_share_a_site(conn):
    # En lo grabado: Forum Tepic y Forum Tepic Platino (Cinemex), Galerías Mall Hermosillo y su VIP (Cinépolis).
    conn, _ = conn
    sites = analytics.cinema_sites(conn, "2026-09-25", "2026-10-07", from_now=False)
    by_names = {tuple(r["cinema_name"] for r in s["cinemas"]): s for s in sites}
    assert ("Forum Tepic", "Forum Tepic Platino") in by_names
    assert ("Galerías Mall Hermosillo", "Galerías Mall Hermosillo VIP") in by_names      # el VIP se distingue por su id
    assert sum(len(s["cinemas"]) for s in sites) == len(analytics.cinema_map(conn, "2026-09-25", "2026-10-07", from_now=False))
    assert len(sites) == sum(len(s["cinemas"]) for s in sites) - 2
