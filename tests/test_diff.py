"""Pruebas del diff de snapshots: cierres (expired / removed) y cambio de fecha."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import diff  # noqa: E402

TAKEN = "2026-09-09T20:00:00+00:00"   # 14:00 CDMX


def row(show_id, dt, **extra):
    base = {"chain": "cinepolis", "show_id": show_id, "cinema_id": "c1", "movie_id": "m1", "movie_title": "Peli",
            "date": dt[:10], "datetime_local": dt, "screen": "3", "language": "spanish", "format": "2D",
            "experience": "", "premium_tier": "", "availability": "", "first_seen": "2026-09-08T14:00:00+00:00"}
    base.update(extra)
    return base


def kinds(events):
    return sorted((e["kind"], e["show_id"]) for e in events)


def test_started_function_is_expired_and_keeps_first_seen():
    prev = {"a": row("a", "2026-09-09T13:30:00")}          # empezó hace 30 min
    events = diff.diff("cinepolis", prev, {}, 2, 1, TAKEN)
    assert kinds(events) == [("expired", "a")]
    assert events[0]["after"] is None
    assert events[0]["before"]["first_seen"] == "2026-09-08T14:00:00+00:00"


def test_future_function_missing_is_removed():
    prev = {"b": row("b", "2026-09-09T19:00:00")}          # faltaban 5 h
    events = diff.diff("cinepolis", prev, {}, 2, 1, TAKEN)
    assert kinds(events) == [("removed", "b")]
    assert events[0]["before"]["first_seen"]


def test_about_to_start_is_expired():
    prev = {"c": row("c", "2026-09-09T14:20:00")}          # empieza en 20 min (< 30 de gracia)
    assert kinds(diff.diff("cinepolis", prev, {}, 2, 1, TAKEN)) == [("expired", "c")]


def test_same_id_other_date_closes_previous_and_adds_new():
    prev = {"d": row("d", "2026-09-09T12:00:00")}
    cur = {"d": row("d", "2026-09-16T12:00:00")}
    events = diff.diff("cinepolis", prev, cur, 2, 1, TAKEN)
    assert kinds(events) == [("added", "d"), ("expired", "d")]
    ex = next(e for e in events if e["kind"] == "expired")
    assert ex["date"] == "2026-09-09" and ex["before"]["first_seen"]


def test_moved_strips_first_seen_from_both_sides():
    prev = {"e": row("e", "2026-09-10T12:00:00")}
    cur = {"e": row("e", "2026-09-10T12:30:00")}
    events = diff.diff("cinepolis", prev, cur, 2, 1, TAKEN)
    assert kinds(events) == [("moved", "e")]
    assert "first_seen" not in events[0]["before"] and "first_seen" not in events[0]["after"]


def test_closing_kind_rules():
    assert diff.closing_kind("2026-09-09T13:30:00", TAKEN) == "expired"     # ya empezó
    assert diff.closing_kind("2026-09-09T14:20:00", TAKEN) == "expired"     # empieza dentro de la gracia
    assert diff.closing_kind("2026-09-09T19:00:00", TAKEN) == "removed"     # faltaban horas
    assert diff.closing_kind(None, TAKEN) == "removed"


def test_changed_fields_ignores_unknown_screen():
    a, b = row("f", "2026-09-10T12:00:00", screen=""), row("f", "2026-09-10T12:00:00", screen="4")
    assert diff.changed_fields(a, b, ("datetime_local", "screen")) == []
    c = row("f", "2026-09-10T12:30:00", screen="5")
    assert diff.changed_fields(b, c, ("datetime_local", "screen", "availability")) == ["datetime_local", "screen"]
