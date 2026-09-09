"""Motor de historia del archivo histórico (sync/state.py): el plan es puro y se prueba con filas sintéticas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync import state  # noqa: E402

TAKEN = "2026-09-09T20:00:00+00:00"   # 14:00 CDMX


def row(show_id, dt, **extra):
    base = {"chain": "cinepolis", "show_id": show_id, "cinema_id": "c1", "cinema_name": "Cine 1", "lat": "19.3", "lng": "-99.1",
            "movie_id": "m1", "movie_title": "Peli", "title_norm": "peli", "genre": "", "rating": "A", "duration_min": 100,
            "distributor": "", "date": dt[:10], "datetime_local": dt, "screen": "3", "language": "spanish", "language_raw": "ESP",
            "format": "2D", "experience": "", "premium_tier": "traditional", "version_raw": "", "availability": ""}
    base.update(extra)
    return base


def open_state(*rows):
    return {(r["show_id"], r["date"]): dict(r) for r in rows}


def test_new_function_is_added_with_catalog():
    p = state.plan("cinepolis", {}, [row("a", "2026-09-10T12:00:00")], TAKEN)
    assert [r["show_id"] for r in p["new"]] == ["a"] and not p["close"] and not p["versions"]
    assert "c1" in p["cinemas"] and "m1" in p["movies"]


def test_missing_function_closes_with_kind():
    started = row("a", "2026-09-09T13:30:00")      # ya empezó → expired
    future = row("b", "2026-09-09T19:00:00")       # faltaban horas → removed
    p = state.plan("cinepolis", open_state(started, future), [], TAKEN)
    assert sorted((prev["show_id"], kind) for prev, kind in p["close"]) == [("a", "expired"), ("b", "removed")]


def test_recycled_id_on_other_date_closes_old_and_adds_new():
    old = row("a", "2026-09-09T12:00:00")
    p = state.plan("cinepolis", open_state(old), [row("a", "2026-09-16T12:00:00")], TAKEN)
    assert [r["date"] for r in p["new"]] == ["2026-09-16"]
    assert [(prev["date"], kind) for prev, kind in p["close"]] == [("2026-09-09", "expired")]


def test_unknown_screen_becoming_known_is_not_a_version():
    prev = row("a", "2026-09-10T12:00:00", screen="")
    p = state.plan("cinepolis", open_state(prev), [row("a", "2026-09-10T12:00:00", screen="4")], TAKEN)
    assert not p["versions"] and p["unchanged"] == 1


def test_time_or_availability_change_opens_version():
    prev = row("a", "2026-09-10T12:00:00")
    p = state.plan("cinepolis", open_state(prev), [row("a", "2026-09-10T12:30:00")], TAKEN)
    assert [r["show_id"] for r in p["versions"]] == ["a"]
    p = state.plan("cinepolis", open_state(prev), [row("a", "2026-09-10T12:00:00", availability="#FFBE06")], TAKEN)
    assert len(p["versions"]) == 1


def test_movie_change_is_identity_not_version():
    prev = row("a", "2026-09-10T12:00:00")
    p = state.plan("cinepolis", open_state(prev), [row("a", "2026-09-10T12:00:00", movie_id="m2")], TAKEN)
    assert [r["movie_id"] for r in p["identity"]] == ["m2"] and not p["versions"]


def test_rows_without_time_are_skipped():
    p = state.plan("cinepolis", {}, [row("a", "2026-09-10T12:00:00", datetime_local="")], TAKEN)
    assert not p["new"]


def test_refresh_open_applies_plan():
    prev = row("a", "2026-09-09T13:30:00"); keep = row("b", "2026-09-10T12:00:00")
    st = open_state(prev, keep)
    p = state.plan("cinepolis", st, [row("b", "2026-09-10T12:45:00"), row("c", "2026-09-10T15:00:00")], TAKEN)
    state.refresh_open(st, p)
    assert set(st) == {("b", "2026-09-10"), ("c", "2026-09-10")} and st[("b", "2026-09-10")]["datetime_local"] == "2026-09-10T12:45:00"


def test_cinema_cities_from_raw():
    cp = {"city_id": "cdmx", "cinemas": [{"id": "cinepolis-x"}, {"id": "cinepolis-y"}]}
    assert state.cinema_cities("cinepolis", cp) == {"cinepolis-x": "cdmx", "cinepolis-y": "cdmx"}
    cx = {"areas": [{"days": [{"data": {"cinemas": [{"id": 26, "state": {"id": 8}}, {"id": 27}]}}]}]}
    assert state.cinema_cities("cinemex", cx) == {"26": "8", "27": None}
