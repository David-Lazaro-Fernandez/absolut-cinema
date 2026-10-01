"""`deploy/update.sh` real contra un clon temporal. `sudo`, `systemctl`, `curl` y `sleep` son dobles en el PATH.
El `systemctl restart` doble corre el `ExecStartPre` de la unidad real."""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

_FAKES = {
    # `sudo -u absolut cmd` → `cmd`
    "sudo": 'shift 2; exec "$@"',
    "curl": 'exit "${CURL_EXIT:-0}"',
    "sleep": "exit 0",
    "systemctl": """echo "$*" >> "$CALLS"
[ "$1" = restart ] || exit 0
shift
for unit in "$@"; do
  pre="$(sed -n "s/^ExecStartPre=-\\/bin\\/sh -c '\\(.*\\)'$/\\1/p" "$REPO/deploy/$unit.service")"
  sh -c "$pre"
done""",
}


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def _commit(cwd, name):
    (cwd / name).write_text(name)
    _git(cwd, "add", name)
    _git(cwd, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", name)
    return _git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def server(tmp_path):
    """Un `origin` con rama `stable`, el clon del servidor en `app/` y una función que corre update.sh."""
    origin, app, bin_dir = tmp_path / "origin", tmp_path / "app", tmp_path / "bin"
    origin.mkdir(); bin_dir.mkdir()
    _git(origin, "init", "-q", "-b", "stable")
    _commit(origin, "a")
    _git(tmp_path, "clone", "-q", str(origin), str(app))
    (app / "data" / "logs").mkdir(parents=True)
    for name, body in _FAKES.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    calls = tmp_path / "calls"

    def run(curl_exit=0):
        calls.write_text("")
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "APP": str(app), "REPO": str(REPO),
               "CALLS": str(calls), "CURL_EXIT": str(curl_exit)}
        res = subprocess.run(["bash", str(REPO / "deploy" / "update.sh")], env=env, capture_output=True, text=True)
        restarts = [line.split()[1:] for line in calls.read_text().splitlines() if line.startswith("restart")]
        return res.returncode, restarts

    def ran(svc):
        return (app / "data" / "run" / f"{svc}.commit").read_text().strip()

    def log():
        path = app / "data" / "logs" / "deploy.log"
        return path.read_text() if path.exists() else ""

    return origin, app, run, ran, log


def test_a_new_stable_commit_restarts_both_and_records_it(server):
    origin, app, run, ran, log = server
    new = _commit(origin, "b")
    assert run() == (0, [["absolut-cinema-dashboard", "absolut-cinema-api"]])
    assert ran("api") == ran("dashboard") == new == _git(app, "rev-parse", "HEAD")
    assert "desplegado" in log()


def test_nothing_new_and_nothing_stale_stays_silent(server):
    _, _, run, _, log = server
    # Sin archivos de commit: reinicia ambos.
    run()
    before = log()
    assert run() == (0, [])
    assert log() == before


def test_a_manual_pull_restarts_only_the_stale_service(server):
    origin, app, run, ran, log = server
    run()
    old, new = ran("api"), _commit(origin, "b")
    # Un `git pull` a mano en el servidor.
    _git(app, "pull", "-q")
    # El dashboard ya corre el commit nuevo.
    (app / "data" / "run" / "dashboard.commit").write_text(new + "\n")
    assert run() == (0, [["absolut-cinema-api"]])
    assert ran("api") == new
    assert f"api ejecutaba {old[:7]}, disco en {new[:7]}: reiniciada" in log()


def test_a_restart_that_does_not_come_back_fails(server):
    _, _, run, _, log = server
    code, restarts = run(curl_exit=7)
    # Para en el primer fallo.
    assert code == 1 and restarts == [["absolut-cinema-api"]]
    assert "ERROR" in log()
