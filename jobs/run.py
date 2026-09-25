"""Ejecuta un trabajo del registro por llave.

Uso: python3 -m jobs.run LLAVE      (lo llaman `make job KEY=…`, las unidades de systemd y los agentes de launchd)

Por corrida:
  - toma un candado por llave (`data/locks/{llave}.lock`); si el mismo trabajo ya está corriendo (el timer y una corrida
    a mano), no corre y lo registra como `skipped`;
  - lanza cada paso como subproceso con su intérprete, en orden y todos aunque uno falle;
  - corta el trabajo completo al llegar a `timeout_min` (el paso en curso y todo lo que lanzó);
  - si falló y la entrada tiene `retries`, repite el trabajo tras `retry_delay_s`;
  - escribe una línea JSON en `data/logs/jobs.jsonl`: inicio, fin, duración, resultado, código de salida, intentos y el
    pico de memoria del paso más pesado (`max_rss_mb`), y una línea legible en la salida estándar.
Sale con 0 si todo salió bien (o si se saltó), 124 si se cortó por tiempo y, si no, con el código del primer paso que
falló, para que systemd y launchd marquen el trabajo como fallido.
"""
import argparse
import fcntl
import json
import os
import resource
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

from scraper import config

from . import keys, registry

LOCK_DIR = config.DATA_DIR / "locks"
LOG_PATH = config.LOG_DIR / "jobs.jsonl"
VENV_PYTHON = config.ROOT / ".venv" / "bin" / "python"
TIMEOUT_EXIT = 124           # la misma convención que `timeout(1)`
KILL_GRACE_S = 30            # tras SIGTERM, cuánto se espera antes de SIGKILL


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _owned_like_parent(path):
    # `deploy` corre como root; sin esto el log y los candados quedarían de root y los demás trabajos (usuario
    # absolut) ya no podrían escribirlos.
    if os.geteuid() == 0:
        st = path.parent.stat()
        os.chown(path, st.st_uid, st.st_gid)


def argv(step):
    """La línea de comandos de un paso del registro."""
    interpreter, target, *args = step
    if interpreter == "python":
        return [sys.executable, "-m", target, *args]
    if interpreter == "venv":
        return [str(VENV_PYTHON), "-m", target, *args]
    return ["bash", str(config.ROOT / target), *args]


def _lock(key):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCK_DIR / f"{key}.lock"
    fh = open(path, "a")
    _owned_like_parent(path)
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    return fh


def _run_step(step, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return "timeout", None
    # Grupo de procesos propio: al cortar por tiempo cae el paso y lo que lanzó (bash → aws, python → hilos).
    proc = subprocess.Popen(argv(step), cwd=config.ROOT, start_new_session=True)
    try:
        code = proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        return "timeout", proc.returncode
    return ("ok" if code == 0 else "failed"), code


def _max_rss_mb():
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # Linux lo da en KiB y macOS en bytes.
    return round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def _record(row):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _owned_like_parent(LOG_PATH)
    mem = f", {row['max_rss_mb']} MB" if row.get("max_rss_mb") is not None else ""
    print(f"{row['finished_at']} jobs {row['key']}: {row['status']} en {row['duration_s']:.0f} s{mem}", flush=True)


def run(key):
    """Corre el trabajo `key` con su candado, tope y reintentos; devuelve el código de salida."""
    e = registry.entry(key)
    base = {"key": key, "area": e["area"], "host": socket.gethostname(), "started_at": _now()}
    lock = _lock(key)
    if lock is None:
        _record({**base, "finished_at": _now(), "duration_s": 0.0, "status": "skipped", "exit_code": 0,
                 "attempts": 0, "max_rss_mb": None, "steps": []})
        return 0
    t0 = time.monotonic()
    deadline = t0 + e["timeout_min"] * 60
    try:
        for attempt in range(1, e["retries"] + 2):
            results = [_run_step(step, deadline) for step in e["steps"]]
            statuses = [s for s, _ in results]
            status = "timeout" if "timeout" in statuses else "failed" if "failed" in statuses else "ok"
            if status != "failed" or attempt > e["retries"]:
                break
            time.sleep(e["retry_delay_s"])
        codes = [c for s, c in results if s == "failed"]
        exit_code = 0 if status == "ok" else TIMEOUT_EXIT if status == "timeout" else codes[0]
        _record({**base, "finished_at": _now(), "duration_s": round(time.monotonic() - t0, 1), "status": status,
                 "exit_code": exit_code, "attempts": attempt, "max_rss_mb": _max_rss_mb(), "steps": statuses})
        return exit_code
    finally:
        lock.close()


def main(argv_=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", choices=keys.ALL)
    return run(ap.parse_args(argv_).key)


if __name__ == "__main__":
    sys.exit(main())
