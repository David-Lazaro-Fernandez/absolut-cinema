"""La Cineteca se captura en las mismas tablas que Cinemex y Cinépolis, pero no entra al head-to-head: con zona nacional o
con plaza, ninguna función comparativa de `analytics/` la devuelve ni la cuenta en sus totales. Las funciones que piden
una cadena explícita (`chain="cineteca"`) sí la ven."""
import pytest

import analytics
from analytics import plaza as plaza_scope

D0, D1 = "2026-09-25", "2026-10-07"      # la semana grabada de Cinemex y Cinépolis, y el día grabado de la Cineteca
_HEAD_TO_HEAD = {
    "kpis": lambda c, p: analytics.kpis(c, D0, D1, from_now=False, plaza=p),
    "mix": lambda c, p: analytics.mix(c, D0, D1, from_now=False, plaza=p),
    "concentration": lambda c, p: analytics.concentration(c, D0, D1, from_now=False, plaza=p),
    "movies_by_chain": lambda c, p: analytics.movies_by_chain(c, D0, D1, from_now=False, limit=500, plaza=p),
    "heatmap_day_slot": lambda c, p: analytics.heatmap_day_slot(c, D0, D1, from_now=False, plaza=p),
    "showtimes_by_slot": lambda c, p: analytics.showtimes_by_slot(c, D0, D1, from_now=False, plaza=p),
    "general_summary": lambda c, p: analytics.general_summary(c, D0, D1, from_now=False, plaza=p),
    "coverage": lambda c, p: analytics.coverage(c, plaza=p),
    "capacity_summary": lambda c, p: analytics.capacity_summary(c, plaza=p),
    "recent_events": lambda c, p: analytics.recent_events(c, kinds=("added",), plaza=p),
    "findings": lambda c, p: analytics.findings(c, D0, D1, plaza=p),
    "conclusions": lambda c, p: analytics.conclusions(c, D0, D1, plaza=p),
}


def _add_samples(conn):
    """Aforo y planos sintéticos de una sala de cada cadena, para las funciones que leen el muestreo."""
    for chain, cinema_id, screen in (("cinepolis", "hermosillo-galerias", "1"), ("cineteca", "001", "Sala 1")):
        conn.execute("INSERT INTO auditorium (chain, cinema_id, screen, seats, broken, sampled_at) VALUES (?, ?, ?, 120, 0, ?)",
                     (chain, cinema_id, screen, "2026-09-26T20:00:00+00:00"))
        conn.execute("""INSERT INTO occupancy_sample (chain, show_id, cinema_id, screen, movie_title, datetime_local, sampled_at,
                                                      minutes_to_start, seats, sold, broken, sold_pct)
                        VALUES (?, ?, ?, ?, 'Cocodrilos', '2026-09-26T18:00:00', '2026-09-26T19:10:00+00:00', -10, 120, 90, 0, 75.0)""",
                     (chain, f"{cinema_id}:1", cinema_id, screen))


def _in_cdmx(conn):
    # Los cines grabados de Cinemex están en Sonora; para probar la plaza se mudan a un área de CDMX.
    conn.execute("UPDATE current_showtime SET city_id = '15' WHERE chain = 'cinemex'")
    conn.execute("UPDATE cinema SET city_id = '15' WHERE chain = 'cinemex'")


@pytest.fixture
def pair(capture_db):
    """(base con las dos cadenas comparables, base con las tres), con el mismo muestreo sintético."""
    two, three = capture_db("cinemex", "cinepolis"), capture_db("cinemex", "cinepolis", "cineteca")
    for conn in (two, three):
        _add_samples(conn)
        _in_cdmx(conn)
    assert three.execute("SELECT COUNT(*) FROM current_showtime WHERE chain = 'cineteca'").fetchone()[0] > 0
    return two, three


@pytest.mark.parametrize("plaza", [None, "cdmx"])
@pytest.mark.parametrize("name", sorted(_HEAD_TO_HEAD))
def test_the_cineteca_changes_nothing_in_the_head_to_head(pair, name, plaza):
    two, three = pair
    fn = _HEAD_TO_HEAD[name]
    got = fn(three, plaza)
    assert got == fn(two, plaza)
    rows = got if isinstance(got, list) else []
    assert all(r.get("chain") != "cineteca" for r in rows)


def test_explicit_chain_functions_see_the_cineteca(pair):
    _, three = pair
    assert [r["cinema_name"] for r in analytics.occupancy_recent(three, chain="cineteca")] == ["Cineteca Chapultepec"]
    assert [r["cinema_name"] for r in analytics.occupancy_recent(three, chain="cineteca", plaza="cdmx")] == ["Cineteca Chapultepec"]
    assert [r["cinema_id"] for r in analytics.capacity_by_cinema(three, chain="cineteca")] == ["001"]
    assert analytics.cinemas(three, chain="cineteca", plaza="cdmx")
    assert all(r["cinema_name"] != "Cineteca Chapultepec" for r in analytics.occupancy_recent(three))


def test_a_chain_outside_the_plaza_matches_nothing():
    assert plaza_scope.plaza_where("gdl", chains=("cineteca",)) == (" AND 0", [])
    assert plaza_scope.plaza_cinema_where("gdl", chains=("cineteca",)) == (" AND 0", [])
    assert plaza_scope.plaza_where(None, "s.") == (" AND s.chain IN (?,?)", ["cinemex", "cinepolis"])
