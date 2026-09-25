"""Pruebas de la Capa 1: movimientos de programación (replay de eventos), orden por fuerza y frescura."""
import importlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import queries  # noqa: E402

findings = importlib.import_module("analytics.findings")   # el paquete exporta la función con el mismo nombre

NOW = datetime.now(timezone.utc)
DAY = (NOW + timedelta(days=2)).date().isoformat()
OLD = (NOW - timedelta(hours=100)).isoformat(timespec="seconds")


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")


def show(show_id, title, cinema_id="a", hhmm="15:00", first_seen=OLD):
    local = f"{DAY}T{hhmm}:00"
    utc = (datetime.fromisoformat(local + "+00:00") + timedelta(hours=6)).isoformat()      # CDMX es UTC−6
    return {"chain": "cinepolis", "show_id": show_id, "cinema_id": cinema_id, "date": DAY, "datetime_local": local,
            "datetime_utc": utc, "title_norm": title, "movie_title": title.title(),
            "city_id": "cdmx", "first_seen": first_seen}


def db(current, events):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE snapshot (id INTEGER PRIMARY KEY, chain TEXT, taken_at TEXT, ok INTEGER)")
    conn.execute("INSERT INTO snapshot (chain, taken_at, ok) VALUES ('cinepolis', ?, 1)", (OLD,))
    cols = list(show("x", "x"))
    conn.execute(f"CREATE TABLE current_showtime ({', '.join(cols)})")
    conn.executemany(f"INSERT INTO current_showtime VALUES ({', '.join('?' for _ in cols)})", [[r[c] for c in cols] for r in current])
    conn.execute("""CREATE TABLE event (id INTEGER PRIMARY KEY, chain TEXT, show_id TEXT, kind TEXT, detected_at TEXT,
                    cinema_id TEXT, date TEXT, before_json TEXT)""")
    for kind, row, detected_at, before in events:
        conn.execute("INSERT INTO event (chain, show_id, kind, detected_at, cinema_id, date, before_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("cinepolis", row["show_id"], kind, detected_at, row["cinema_id"], row["date"], json.dumps(before) if before else None))
    return conn


def test_programming_moves_replays_changes_on_published_days_only():
    xs = [show(f"x{i}", "equis") for i in range(10)]
    ys = [show(f"y{i}", "ye") for i in range(10)]
    new_y = show("y_new", "ye", first_seen=ago(40))
    other_cinema = show("b1", "equis", cinema_id="b", first_seen=ago(40))    # cine que no estaba publicado en el corte
    moved = show("y0", "ye", hhmm="21:00")
    current = xs[1:] + [moved] + ys[1:] + [new_y, other_cinema]
    events = [("added", new_y, ago(40), None), ("added", other_cinema, ago(40), None),
              ("removed", xs[0], ago(30), xs[0]), ("moved", moved, ago(20), ys[0])]
    out = {r["title_norm"]: r for r in queries.programming_moves(db(current, events), DAY, DAY)}
    assert (out["equis"]["shows_then"], out["equis"]["shows_now"], out["equis"]["removed"]) == (10, 9, 1)
    assert (out["ye"]["shows_then"], out["ye"]["shows_now"], out["ye"]["added"], out["ye"]["moved"]) == (10, 11, 1, 1)
    assert (out["equis"]["delta_pp"], out["ye"]["delta_pp"]) == (-5.0, 5.0)
    since = datetime.fromisoformat(out["ye"]["since"])
    assert abs((since - (NOW - timedelta(hours=72))).total_seconds()) < 60      # el corte de 72 h, no el de publicación


def test_programming_moves_is_empty_while_the_week_is_being_published():
    fresh = [show(f"x{i}", "equis", first_seen=ago(2)) for i in range(10)]
    assert queries.programming_moves(db(fresh, [("added", r, ago(2), None) for r in fresh]), DAY, DAY) == []


def test_findings_keeps_the_strongest(monkeypatch):
    def rule(topic, strength):
        return lambda *a, **k: {"topic": topic, "strength": strength}
    monkeypatch.setattr(findings, "kpis", lambda *a, **k: [{"chain": "cinemex"}, {"chain": "cinepolis"}])
    monkeypatch.setattr(findings, "movies_by_chain", lambda *a, **k: [])
    monkeypatch.setattr(findings, "_moves_finding", rule("movimientos", 1.2))
    monkeypatch.setattr(findings, "_demand_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "_price_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "_presale_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "_presale_gap_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "_presale_exclusive_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "_title_finding", rule("titulo", 2.0))
    monkeypatch.setattr(findings, "_concentration_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "_concession_finding", rule("dulceria", 5.0))
    monkeypatch.setattr(findings, "_slot_finding", rule("franjas", 3.0))
    monkeypatch.setattr(findings, "_format_finding", rule("formato", 1.1))
    monkeypatch.setattr(findings, "_exclusive_finding", rule("exclusivas", 2.0))
    out = findings.findings(None, DAY, DAY, top=4)
    assert [f["topic"] for f in out] == ["dulceria", "franjas", "titulo", "exclusivas"]   # empate: orden de evaluación
    assert all("as_of" in f for f in out)


def test_freshness():
    assert findings._is_fresh(ago(24), 3)
    assert not findings._is_fresh(ago(24 * 4), 3)
    assert not findings._is_fresh(None, 3)


def _next_friday():
    d = NOW.date() + timedelta(days=1)
    return (d + timedelta(days=(4 - d.weekday()) % 7)).isoformat()


def test_effective_ticket_price_weights_by_programming():
    seats = importlib.import_module("analytics.seats")
    fri = _next_friday()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE current_showtime (chain, date, datetime_local, datetime_utc, premium_tier, experience,
                    format, city_id)""")
    shows = [("cinemex", "")] * 3 + [("cinemex", "platinum")]
    conn.executemany("INSERT INTO current_showtime VALUES (?, ?, ?, ?, ?, '', '2D', '15')",
                     [(c, fri, f"{fri}T18:00:00", f"{fri}T23:59:00+00:00", tier) for c, tier in shows])
    conn.execute("""CREATE TABLE price_sample (chain, cinema_id, format_bucket, day_type, general_cents, sampled_at)""")
    conn.executemany("INSERT INTO price_sample VALUES ('cinemex', 'c1', ?, 'weekend', ?, ?)",
                     [("traditional", 8000, ago(24)), ("premium", 16000, ago(24))])
    out = seats.effective_ticket_price(conn, fri, fri)
    assert out == [{"chain": "cinemex", "shows": 4, "shows_priced": 4, "last_sampled": ago(24), "pct_priced": 100.0,
                    "avg_price": 100.0}]


def test_occupancy_by_title_compares_against_its_own_time_slot():
    seats = importlib.import_module("analytics.seats")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE occupancy_sample (id INTEGER PRIMARY KEY, chain, cinema_id, movie_title, datetime_local,
                    minutes_to_start, seats, sold, sampled_at)""")
    fri = _next_friday()
    rows = [("Alta", f"{fri}T19:00:00", 30), ("Alta", f"{fri}T19:30:00", 30),
            ("Baja", f"{fri}T19:00:00", 10), ("Baja", f"{fri}T20:00:00", 10),
            ("Matiné", f"{fri}T11:00:00", 5)]          # otra franja: no mueve lo esperado de la noche
    conn.executemany("INSERT INTO occupancy_sample (chain, cinema_id, movie_title, datetime_local, minutes_to_start, seats, sold, sampled_at) "
                     "VALUES ('cinepolis', 'c1', ?, ?, -30, 100, ?, ?)", [(t, dt, sold, ago(5)) for t, dt, sold in rows])
    out = {r["title_norm"]: r for r in seats.occupancy_by_title(conn, min_samples=1)}
    assert (out["alta"]["expected_pct"], out["alta"]["demand_index"]) == (20.0, 1.5)
    assert out["baja"]["demand_index"] == 0.5
    assert out["matine"]["demand_index"] == 1.0
