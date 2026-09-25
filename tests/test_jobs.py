"""Registro de trabajos (`jobs/`): coherencia de llaves y entradas, horarios, que lo generado en deploy/systemd/ y
ARCHITECTURE.md coincida con el registro, y el runner (resultado, reintentos, tope, candado y registro por corrida)
con comandos locales de un segundo, sin red."""
import fcntl
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs import keys, registry, units  # noqa: E402
from jobs import run as job_run  # noqa: E402
from scraper import config, health  # noqa: E402


def test_every_key_has_an_entry_and_an_area():
    registry.validate()
    assert set(registry.REGISTRY) == set(keys.AREA) == set(keys.ALL)


def test_generated_units_and_doc_match_the_registry():
    # Si falla: `make units` y versionar el resultado.
    assert units.check() == []


@pytest.mark.parametrize("spec, parsed", [
    ("07:30", {"weekday": None, "day": None, "hour": 7, "minute": 30}),
    ("*:50", {"weekday": None, "day": None, "hour": None, "minute": 50}),
    ("Sun 04:07", {"weekday": 6, "day": None, "hour": 4, "minute": 7}),
    ("1 04:07", {"weekday": None, "day": 1, "hour": 4, "minute": 7}),
])
def test_parse_schedule(spec, parsed):
    assert registry.parse_schedule(spec) == parsed


@pytest.mark.parametrize("spec", ["25:00", "07:60", "31 04:07"])
def test_parse_schedule_rejects_bad_specs(spec):
    with pytest.raises(registry.RegistryError):
        registry.parse_schedule(spec)


def test_daily_times_are_what_health_expects():
    assert registry.daily_times(keys.SNAPSHOT) == ("07:30", "13:30", "20:30")
    assert registry.daily_times(keys.AUTH_PRUNE) == ()         # semanal: no cuenta como captura diaria


def test_calendar_translations():
    assert units._on_calendar("Sun 04:07") == "Sun *-*-* 04:07:00"
    assert units._on_calendar("1 04:07") == "*-*-01 04:07:00"
    assert units._on_calendar("*:22") == "*-*-* *:22:00"
    assert registry.describe_schedule(("*:22", "*:52")) == "cada hora a :22 y :52"
    plist = units.plist({**registry.entry(keys.AUTH_PRUNE), "schedule": ("Sun 04:07",)}, "/repo")
    assert "<key>Weekday</key><integer>0</integer>" in plist      # launchd: domingo es 0
    assert "<string>KEY=auth-prune</string>" in plist


def test_disabled_jobs_stay_off(monkeypatch):
    monkeypatch.setitem(registry.REGISTRY, keys.CALIBRATE_CINEMEX, {**registry.REGISTRY[keys.CALIBRATE_CINEMEX], "enabled": False})
    enabled = [e["key"] for e in registry.entries(host="server") if e["enabled"]]
    assert keys.CALIBRATE_CINEMEX not in enabled and keys.SNAPSHOT in enabled


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Runner con candados y log en un directorio temporal y un trabajo falso cuyos pasos son comandos de shell."""
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(job_run, "LOG_PATH", tmp_path / "logs" / "jobs.jsonl")
    monkeypatch.setattr(job_run, "LOCK_DIR", tmp_path / "locks")
    monkeypatch.setattr(job_run, "argv", lambda step: ["sh", "-c", step[1]])
    job = {}

    def fake_entry(key):
        return {**registry.DEFAULTS, "key": key, "area": keys.AREA[key], "steps": (("python", "true"),), **job}

    monkeypatch.setattr(registry, "entry", fake_entry)

    def last_row():
        return json.loads((tmp_path / "logs" / "jobs.jsonl").read_text().splitlines()[-1])

    return job, last_row, tmp_path


def test_run_ok_records_duration_and_memory(sandbox):
    job, last_row, _ = sandbox
    assert job_run.run(keys.HEALTH) == 0
    row = last_row()
    assert row["key"] == "health" and row["status"] == "ok" and row["exit_code"] == 0 and row["attempts"] == 1
    assert row["max_rss_mb"] is not None and row["steps"] == ["ok"]


def test_run_keeps_going_and_reports_first_failure(sandbox):
    job, last_row, _ = sandbox
    job["steps"] = (("python", "exit 3"), ("python", "true"), ("python", "exit 5"))
    assert job_run.run(keys.PRICES) == 3
    assert last_row()["steps"] == ["failed", "ok", "failed"]


def test_run_retries_a_failed_job(sandbox):
    job, last_row, tmp = sandbox
    marker = tmp / "first"
    # Falla la primera vez y pasa la segunda.
    job.update(steps=(("python", f"test -f {marker} || {{ touch {marker}; exit 1; }}"),), retries=1, retry_delay_s=0)
    assert job_run.run(keys.BACKUP) == 0
    assert last_row()["attempts"] == 2 and last_row()["status"] == "ok"


def test_run_cuts_at_the_timeout(sandbox):
    job, last_row, _ = sandbox
    job.update(steps=(("python", "sleep 10"), ("python", "true")), timeout_min=1 / 60)
    assert job_run.run(keys.SEATS) == job_run.TIMEOUT_EXIT
    row = last_row()
    assert row["status"] == "timeout" and row["duration_s"] < 5 and row["steps"] == ["timeout", "timeout"]


def test_run_skips_when_the_same_job_is_running(sandbox):
    job, last_row, tmp = sandbox
    (tmp / "locks").mkdir()
    with open(tmp / "locks" / "snapshot.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert job_run.run(keys.SNAPSHOT) == 0
    assert last_row()["status"] == "skipped"


def test_health_jobs_status_reads_the_run_log(sandbox):
    job, _, _ = sandbox
    job_run.run(keys.HEALTH)
    job["steps"] = (("python", "exit 2"),)
    job_run.run(keys.HEALTH)
    status = {s["key"]: s for s in health.jobs_status(days=1)}
    assert status["health"]["runs"] == 2 and status["health"]["failures"] == 1 and status["health"]["last_status"] == "failed"
    assert status["snapshot"]["runs"] == 0 and status["snapshot"]["last_status"] is None
