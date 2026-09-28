"""El pase post-inicio (`scraper.sample`): el orden intercalado por cine y el tiempo límite, sin tocar la red."""
import random
import sqlite3

from scraper import sample, store


def _row(show_id, cinema_id):
    return {"show_id": show_id, "cinema_id": cinema_id, "screen": "1", "movie_id": "m", "movie_title": "T",
            "datetime_local": "2026-09-28T13:00:00", "availability": None}


def test_interleave_gives_every_cinema_a_turn_before_repeating_one():
    rows = [_row(f"a{i}", "a") for i in range(5)] + [_row(f"b{i}", "b") for i in range(2)] + [_row("c0", "c")]
    out = sample.interleave_by_cinema(rows, rng=random.Random(7))
    assert sorted(r["show_id"] for r in out) == sorted(r["show_id"] for r in rows)
    assert {r["cinema_id"] for r in out[:3]} == {"a", "b", "c"}
    assert {r["cinema_id"] for r in out[3:5]} == {"a", "b"}
    assert [r["cinema_id"] for r in out[5:]] == ["a", "a", "a"]


def test_an_exhausted_budget_stops_the_pass_without_counting_as_failure(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(store.SCHEMA)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(sample.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(sample.time, "sleep", lambda s: None)
    monkeypatch.setattr(sample, "log", lambda msg: None)
    monkeypatch.setattr(sample, "layout_for", lambda chain, row, vids, stats: {"seats": 100, "sold": 40, "broken": 0, "areas": []})
    rows = [_row(str(i), "a") for i in range(10)]
    ok = sample._take_layouts(conn, "cinemex", rows, {"calls": 0}, "post-start", deadline=35)
    assert ok
    assert conn.execute("SELECT count(*) FROM occupancy_sample").fetchone()[0] == 4


def test_a_few_failed_layouts_do_not_fail_the_pass(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(store.SCHEMA)
    monkeypatch.setattr(sample.time, "sleep", lambda s: None)
    monkeypatch.setattr(sample, "log", lambda msg: None)
    monkeypatch.setattr(sample, "layout_for", lambda chain, row, vids, stats: None if row["show_id"] in failing else
                        {"seats": 100, "sold": 40, "broken": 0, "areas": []})
    rows = [_row(str(i), "a") for i in range(8)]
    failing = {"0", "1"}
    assert sample._take_layouts(conn, "cinemex", rows, {"calls": 0}, "post-start")
    failing = {"x0", "x1", "x2"}
    assert not sample._take_layouts(conn, "cinemex", [_row(f"x{i}", "a") for i in range(8)], {"calls": 0}, "post-start")
