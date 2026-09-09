"""Conversiones del sync (sync/copy.py, sync/pg.py) sin Postgres."""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync import copy, pg  # noqa: E402


def test_event_changes_only_tracked_fields():
    before = json.dumps({"screen": "3", "datetime_local": "2026-09-10T12:00:00", "movie_title": "X", "availability": ""})
    after = json.dumps({"screen": "5", "datetime_local": "2026-09-10T12:00:00", "movie_title": "Y", "availability": None})
    assert copy.event_changes(before, after) == {"screen": ["3", "5"]}
    assert copy.event_changes(None, after) is None and copy.event_changes(before, before) is None


def test_type_conversions():
    assert pg.to_ts("2026-09-09T20:00:00+00:00") == datetime(2026, 9, 9, 20, tzinfo=timezone.utc)
    assert pg.to_local("2026-09-10T12:30:00") == datetime(2026, 9, 10, 12, 30)
    assert pg.to_date("2026-09-10T12:30:00") == date(2026, 9, 10)
    assert pg.to_float("19.32") == 19.32 and pg.to_float("") is None and pg.to_float(None) is None
    assert pg.to_int("122.0") == 122 and pg.to_int(None) is None


def test_month_range_and_bucket_path(monkeypatch):
    assert pg.month_range(date(2026, 12, 15)) == (date(2026, 12, 1), date(2027, 1, 1))
    monkeypatch.setattr(copy.config, "BACKUP_BUCKET", "s3://bucket")
    assert copy._bucket_path("data/raw/cinemex/2026-09-09/203005Z.json.gz") == "s3://bucket/raw/cinemex/2026-09-09/203005Z.json.gz"
    monkeypatch.setattr(copy.config, "BACKUP_BUCKET", None)
    assert copy._bucket_path("data/raw/x.json.gz") == "data/raw/x.json.gz"
