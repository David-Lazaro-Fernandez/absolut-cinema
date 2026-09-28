"""La pasada de precios (`scraper.sample.price_pass`) sobre la captura grabada de las tres cadenas: solo pide boletos
de las cadenas con lector (`PRICED_CHAINS`); la Cineteca no tiene y su precio sigue pendiente."""
from datetime import datetime
from zoneinfo import ZoneInfo

from scraper import sample


def test_prices_are_only_asked_to_chains_with_a_ticket_reader(capture_db, monkeypatch):
    conn = capture_db("cinemex", "cinepolis", "cineteca")
    asked = []
    monkeypatch.setattr(sample, "now_local", lambda: datetime(2026, 9, 25, tzinfo=ZoneInfo("America/Mexico_City")))
    monkeypatch.setattr(sample, "cinemex_tickets", lambda show_id, stats: asked.append(("cinemex", show_id)) or [])
    monkeypatch.setattr(sample, "cinepolis_tickets", lambda session_id, vid, stats: asked.append(("cinepolis", session_id)) or [])
    sample.price_pass(conn, days=14)
    cineteca = {r[0] for r in conn.execute("SELECT show_id FROM current_showtime WHERE chain = 'cineteca'")}
    assert {chain for chain, _ in asked} == {"cinemex", "cinepolis"}
    assert not cineteca & {show_id for _, show_id in asked}
