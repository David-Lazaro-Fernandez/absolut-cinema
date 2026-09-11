"""Funciones de estado de `scraper.health` que alimentan la página de operaciones: corridas recientes sobre una base
en memoria, cola de logs sobre archivos temporales y tolerancia a lo que falta (logs inexistentes, sin git)."""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import config, health, store  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(store.SCHEMA)
    yield c
    c.close()


def _snapshot(conn, chain, days_ago, ok=1, error=None):
    at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    conn.execute("INSERT INTO snapshot (chain, taken_at, finished_at, ok, n_shows, calls, duration_s, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (chain, at, at, ok, 100 if ok else None, 9, 12.5, error))


def test_recent_runs_is_windowed_and_newest_first(conn):
    _snapshot(conn, "cinemex", days_ago=10)
    _snapshot(conn, "cinemex", days_ago=2)
    _snapshot(conn, "cinepolis", days_ago=1, ok=0, error="Blocked: 403 html")
    runs = health.recent_runs(conn, days=7)
    assert [r["chain"] for r in runs] == ["cinepolis", "cinemex"]
    assert runs[0]["ok"] == 0 and runs[0]["error"] == "Blocked: 403 html"
    assert set(runs[1]) >= {"id", "taken_at", "n_shows", "calls", "duration_s"}
    assert len(health.recent_runs(conn, days=30)) == 3


def test_log_tail_reads_last_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    (tmp_path / "run.log").write_text("".join(f"línea {i}\n" for i in range(1, 501)), encoding="utf-8")
    tail = health.log_tail("run", lines=3)
    assert tail["lines"] == ["línea 498", "línea 499", "línea 500"]
    assert tail["size_bytes"] > 0 and tail["modified_at"]
    assert health.log_tail("run", lines=1000)["lines"][0] == "línea 1"     # pide más de las que hay: todas


def test_log_tail_handles_missing_and_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    assert health.log_tail("deploy")["lines"] == []
    with pytest.raises(KeyError):
        health.log_tail("../etc/passwd")


def test_deployment_without_git_or_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)                           # no es un clon: commit None, sin explotar
    dep = health.deployment()
    assert dep["commit"] is None and dep["last_deploy"] is None and dep["last_backup"] is None
    (tmp_path / "backup.log").write_text("2026-09-11T05:07:00Z backup ok x.gz\n")
    assert health.deployment()["last_backup"].endswith("backup ok x.gz")


def test_storage_reports_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "snapshots.db")
    (tmp_path / "raw" / "cinemex").mkdir(parents=True)
    (tmp_path / "raw" / "cinemex" / "a.json.gz").write_bytes(b"x" * 10)
    (tmp_path / "snapshots.db").write_bytes(b"y" * 5)
    s = health.storage()
    assert s["db_bytes"] == 5 and s["raw_bytes"] == 10 and s["wal_bytes"] == 0 and s["disk_free_bytes"] > 0
