"""Salud de la captura: un reporte diario que dice si la serie está completa y si el muestreo avanza.

Uso: python3 -m scraper.health [--hours 24] [--json]
Sale con código 1 si hay algún problema, para que el timer/launchd lo marque como fallido. Escribe una
línea por corrida en data/logs/health.log y el detalle en stdout. Solo librería estándar.

Revisa, para cada cadena y la ventana dada:
  - última captura: edad y si terminó bien (umbral MAX_AGE_MIN, el mismo que el aviso del dashboard; la
    cartelera se captura a las horas del trabajo `snapshot` de `jobs.registry`, así que el hueco normal nocturno es de 11 h);
  - unidades de la última captura buena que fallaron (sus cines conservan la captura anterior) y cines sin estado de
    INEGI en scraper/cinema_states.csv;
  - capturas programadas dentro de la ventana que no tienen un snapshot bueno a ±SLOT_TOLERANCE_MIN
    (la Mac dormida o sin red las pierde; en el servidor no debería faltar ninguna), y cuántas fallaron;
  - muestras de ocupación a T−60 y post-inicio, precios de 7 días, y que los pases semanales de dulcería
    (menú de Cinépolis, tiendas a domicilio) no lleven más de 8 días sin renovarse;
  - preventas de ambas cadenas en 24 h y pares de títulos entre cadenas por revisar (scripts/title_pairs.py).

Además expone, para la página de operaciones del dashboard (`views/operaciones.py`), lo que un ingeniero mira al
diagnosticar: las corridas recientes con su resultado (`recent_runs`), cada unidad de captura con sus fallos
(`capture_units`), cada trabajo programado con su última corrida y su
pico de memoria (`jobs_status`, de `data/logs/jobs.jsonl`), la cola de cada log (`log_tail`), el tamaño de
la base y del crudo con el espacio libre (`storage`) y el commit desplegado con el último despliegue y respaldo
(`deployment`). Todo solo lectura y solo librería estándar; `check` y `recent_runs` reciben la conexión, el resto lee
`data/` directamente.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from jobs import keys as job_keys
from jobs import registry as job_registry

from . import config, sample, states, store, titles

MAX_AGE_MIN = 12 * 60        # tres capturas al día: el hueco normal más largo (20:30 → 07:30) es de 11 h
SLOT_TOLERANCE_MIN = 30      # una captura programada cuenta si hay snapshot bueno a ±30 min
COVERAGE_MIN_RATIO = 0.9     # cines en la última captura frente al máximo de 7 días: menos es un estado o ciudad que llegó vacío
CHAINS = ("cinemex", "cinepolis")
# Logs que se pueden consultar desde el dashboard: nombre → archivo en config.LOG_DIR. Lista cerrada a propósito, para
# que la página nunca reciba una ruta arbitraria.
LOGS = {"run": "run.log", "sample": "sample.log", "delivery": "delivery.log", "health": "health.log",
        "deploy": "deploy.log", "backup": "backup.log", "mail": "mail.log", "systemd": "systemd.out", "jobs": "jobs.jsonl"}
JOB_RUN_LINES = 5000         # corridas de jobs.jsonl que se leen (~60 al día: cubre más de un mes)


def _dt(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def scheduled_captures(now, hours):
    """Instantes UTC de las capturas programadas (trabajo `snapshot` del registro, hora de CDMX) que caen en
    la ventana [now − hours, now − tolerancia]: las que ya deberían existir."""
    tz = ZoneInfo(config.PILOT_TIMEZONE)
    start, latest = now - timedelta(hours=hours), now - timedelta(minutes=SLOT_TOLERANCE_MIN)
    day, out = start.astimezone(tz).date(), []
    while datetime(day.year, day.month, day.day, tzinfo=tz) <= latest:
        for hm in job_registry.daily_times(job_keys.SNAPSHOT):
            h, m = (int(x) for x in hm.split(":"))
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=tz).astimezone(timezone.utc)
            if start <= t <= latest:
                out.append(t)
        day += timedelta(days=1)
    return out


def check(conn, hours=24, now=None):
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
    scheduled = scheduled_captures(now, hours)
    report = {"at": now.isoformat(timespec="seconds"), "hours": hours, "chains": {}, "problems": []}
    for chain in CHAINS:
        c = {}
        last = conn.execute("SELECT taken_at, finished_at, ok, n_shows, n_cinemas, error FROM snapshot WHERE chain = ? ORDER BY id DESC LIMIT 1",
                            (chain,)).fetchone()
        if not last:
            report["problems"].append(f"{chain}: sin snapshots"); report["chains"][chain] = c; continue
        age = (now - _dt(last["finished_at"] or last["taken_at"])).total_seconds() / 60
        c["last_at"], c["last_ok"], c["last_age_min"], c["last_shows"] = last["taken_at"], bool(last["ok"]), round(age), last["n_shows"]
        if not last["ok"]:
            report["problems"].append(f"{chain}: la última captura falló ({(last['error'] or '')[:80]})")
        if age > MAX_AGE_MIN:
            report["problems"].append(f"{chain}: última captura hace {age:.0f} min")
        rows = conn.execute("SELECT taken_at, ok FROM snapshot WHERE chain = ? AND taken_at >= ? ORDER BY taken_at", (chain, since)).fetchall()
        good = [_dt(r["taken_at"]) for r in rows if r["ok"]]
        tol = timedelta(minutes=SLOT_TOLERANCE_MIN)
        missing = [t for t in scheduled if not any(abs(g - t) <= tol for g in good)]
        c["snapshots"], c["expected"], c["failed"] = len(rows), len(scheduled), sum(1 for r in rows if not r["ok"])
        c["missing"] = [t.astimezone(ZoneInfo(config.PILOT_TIMEZONE)).strftime("%d/%m %H:%M") for t in missing]
        if c["failed"]:
            report["problems"].append(f"{chain}: {c['failed']} capturas fallidas en {hours} h")
        if missing:
            report["problems"].append(f"{chain}: {len(missing)} captura(s) programada(s) sin snapshot: {', '.join(c['missing'][:4])}")
        occ = conn.execute("""SELECT SUM(minutes_to_start >= 0) pre, SUM(minutes_to_start < 0) post
                              FROM occupancy_sample WHERE chain = ? AND sampled_at >= ?""", (chain, since)).fetchone()
        c["occupancy_t60"], c["occupancy_post_start"] = occ["pre"] or 0, occ["post"] or 0
        week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
        # Cobertura: una captura buena con muchos menos cines que las de la semana significa que un estado o una ciudad
        # respondió vacío (la API contesta 200 igual). El máximo semanal es la referencia, no una constante.
        peak = conn.execute("SELECT MAX(n_cinemas) FROM snapshot WHERE chain = ? AND ok = 1 AND taken_at >= ?", (chain, week_ago)).fetchone()[0]
        c["last_cinemas"], c["peak_cinemas_7d"] = last["n_cinemas"], peak
        # Unidades (estado de Cinemex, lote de Cinépolis) que fallaron en la última captura buena: sus cines quedaron
        # con la cartelera de la captura anterior.
        last_ok = conn.execute("SELECT id FROM snapshot WHERE chain = ? AND ok = 1 ORDER BY id DESC LIMIT 1", (chain,)).fetchone()
        failed_units = conn.execute("SELECT unit, label, error, carried FROM snapshot_unit WHERE snapshot_id = ? AND ok = 0 ORDER BY unit",
                                    (last_ok["id"],)).fetchall() if last_ok else []
        c["failed_units"] = [dict(u) for u in failed_units]
        if failed_units:
            report["problems"].append(f"{chain}: {len(failed_units)} unidad(es) fallaron en la última captura y conservan la anterior: "
                                      + "; ".join(f"{u['label']} ({(u['error'] or '')[:60]})" for u in failed_units[:3]))
        if last["ok"] and peak and (last["n_cinemas"] or 0) < COVERAGE_MIN_RATIO * peak:
            report["problems"].append(f"{chain}: la última captura trae {last['n_cinemas']} cines frente a {peak} en la semana (cobertura incompleta)")
        c["prices_7d"] = conn.execute("SELECT COUNT(*) FROM price_sample WHERE chain = ? AND sampled_at >= ?", (chain, week_ago)).fetchone()[0]
        c["concession_cinemas_8d"] = conn.execute(
            "SELECT COUNT(DISTINCT cinema_id) FROM concession_price WHERE chain = ? AND sampled_at >= ?",
            (chain, (now - timedelta(days=8)).isoformat(timespec="seconds"))).fetchone()[0]
        c["delivery_stores_8d"] = conn.execute(
            "SELECT COUNT(DISTINCT platform || store_id) FROM delivery_price WHERE chain = ? AND sampled_at >= ?",
            (chain, (now - timedelta(days=8)).isoformat(timespec="seconds"))).fetchone()[0]
        # Los pases semanales solo se exigen una vez que han corrido alguna vez.
        if chain == "cinepolis" and not c["concession_cinemas_8d"] and conn.execute("SELECT 1 FROM concession_price LIMIT 1").fetchone():
            report["problems"].append("cinepolis: el menú de dulcería lleva más de 8 días sin renovarse")
        if not c["delivery_stores_8d"] and conn.execute("SELECT 1 FROM delivery_price WHERE chain = ? LIMIT 1", (chain,)).fetchone():
            report["problems"].append(f"{chain}: dulcería a domicilio sin lectura en 8 días")
        c["presale_24h"] = conn.execute("SELECT COUNT(*) FROM presale_sample WHERE chain = ? AND sampled_at >= ?",
                                        (chain, since)).fetchone()[0]
        if not c["presale_24h"] and conn.execute("SELECT 1 FROM presale_sample WHERE chain = ? LIMIT 1", (chain,)).fetchone():
            report["problems"].append(f"{chain}: sin lecturas de preventa en 24 h (¿se cayó el trabajo presale o su lista de preventa?)")
        if chain == "cinemex":
            # El plano público se da por bueno porque "1" coincide con el semáforo. Una lectura a T−60 con disponibilidad
            # alta y más de la mitad vendida diría que "1" ya significa otra cosa (apartados, bloqueos).
            odd = conn.execute("""SELECT COUNT(*) FROM occupancy_sample WHERE chain = ? AND sampled_at >= ? AND minutes_to_start >= 0
                                  AND availability = 'high' AND sold_pct > 50""", (chain, since)).fetchone()[0]
            if odd >= 3:
                report["problems"].append(f"cinemex: {odd} planos a T−60 con disponibilidad alta y más de la mitad vendida: revisar qué marca \"1\" en el plano")
            # Calibración del semáforo: la hace por chunks el trabajo calibrate-cinemex; aquí el avance por nivel.
            have = sample.calibration_progress(conn, chain)
            c["calibration"] = {lvl: have.get(lvl, 0) for lvl in sample.CALIBRATION_LEVELS}
        report["chains"][chain] = c
    # El muestreo de planos corre para ambas cadenas en las plazas de config.SEATS_PLAZAS; si una no tiene ninguna
    # muestra en la ventana, algo se detuvo.
    for chain in ("cinepolis", "cinemex"):
        cp = report["chains"].get(chain, {})
        if cp and cp.get("snapshots") and not cp.get("occupancy_post_start"):
            report["problems"].append(f"{chain}: cero planos post-inicio en la ventana para {', '.join(config.SEATS_PLAZAS)} (¿se cayó el pase de butacas?)")
    # Pares de títulos entre cadenas que las reglas no unen y nadie ha revisado (scripts/title_pairs.py).
    lonely = {chain: {r[0]: {"title": r[1], "duration_min": r[2], "distributor": r[3], "shows": r[4]} for r in conn.execute("""
        SELECT title_norm, MAX(movie_title), MAX(duration_min), MAX(distributor), COUNT(*)
        FROM current_showtime WHERE chain = ? AND title_norm <> '' GROUP BY title_norm""", (chain,))} for chain in CHAINS}
    report["title_candidates"] = len(titles.candidates(lonely["cinemex"], lonely["cinepolis"]))
    if report["title_candidates"]:
        report["problems"].append(f"{report['title_candidates']} par(es) de títulos entre cadenas por revisar "
                                  "(correr scripts/title_pairs.py y aceptar o rechazar)")
    cinemas = [dict(r) for r in conn.execute("SELECT chain, cinema_id, name FROM cinema ORDER BY chain, cinema_id")]
    report["unmapped_cinemas"] = states.unmapped(cinemas)
    if report["unmapped_cinemas"]:
        report["problems"].append(f"{len(report['unmapped_cinemas'])} cine(s) sin estado de INEGI en scraper/cinema_states.csv "
                                  "(correr scripts/cinema_states.py): " + ", ".join(f"{c['chain']} {c['name']}" for c in report["unmapped_cinemas"][:5]))
    report["ok"] = not report["problems"]
    return report


def recent_runs(conn, days=7):
    """Corridas de captura de cartelera de los últimos `days` días, la más reciente primero: resultado, funciones y
    cines leídos, eventos detectados, llamadas a la API, duración y el error literal si falló."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = conn.execute("""SELECT id, chain, taken_at, finished_at, ok, n_shows, n_cinemas, n_events, calls, duration_s, error
                           FROM snapshot WHERE taken_at >= ? ORDER BY id DESC""", (since,)).fetchall()
    return [dict(r) for r in rows]


def capture_units(conn, days=7):
    """Cada unidad de captura (estado de Cinemex, lote de Cinépolis) de los últimos `days` días: su última corrida con
    resultado y error, cuántas veces corrió y falló, y la media de llamadas, duración y funciones leídas. Las fallidas
    recientes primero."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = conn.execute("""
        SELECT u.chain, u.unit, u.label, u.ok, u.error, u.attempts, u.calls, u.duration_s, u.n_cinemas, u.n_shows,
               u.carried, s.taken_at
        FROM snapshot_unit u JOIN snapshot s ON s.id = u.snapshot_id
        WHERE s.taken_at >= ? ORDER BY s.taken_at DESC, u.chain, u.unit""", (since,)).fetchall()
    out = {}
    for r in rows:
        key = (r["chain"], r["unit"])
        if key not in out:
            out[key] = {"chain": r["chain"], "unit": r["unit"], "label": r["label"], "last_at": r["taken_at"],
                        "last_ok": bool(r["ok"]), "last_error": r["error"], "runs": 0, "failures": 0,
                        "_calls": [], "_secs": [], "_shows": []}
        u = out[key]
        u["runs"] += 1
        u["failures"] += 0 if r["ok"] else 1
        u["_calls"].append(r["calls"] or 0)
        u["_secs"].append(r["duration_s"] or 0)
        if r["ok"]:
            u["_shows"].append(r["n_shows"] or 0)
    result = []
    for u in out.values():
        calls, secs, shows = u.pop("_calls"), u.pop("_secs"), u.pop("_shows")
        u["avg_calls"] = round(sum(calls) / len(calls), 1)
        u["avg_duration_s"] = round(sum(secs) / len(secs), 1)
        u["avg_shows"] = round(sum(shows) / len(shows)) if shows else None
        result.append(u)
    return sorted(result, key=lambda u: (u["last_ok"], -u["failures"], u["chain"], u["unit"]))


def log_tail(name, lines=60):
    """Últimas `lines` líneas de un log de `LOGS` (la más reciente al final), con su tamaño y última escritura.
    Un log que aún no existe devuelve la lista vacía, no un error: en un servidor recién instalado faltan varios."""
    if name not in LOGS:
        raise KeyError(f"log desconocido: {name}; opciones: {', '.join(LOGS)}")
    path = config.LOG_DIR / LOGS[name]
    out = {"name": name, "path": str(path), "lines": [], "size_bytes": 0, "modified_at": None}
    if not path.exists():
        return out
    st = path.stat()
    out["size_bytes"], out["modified_at"] = st.st_size, datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
    with open(path, "rb") as fh:
        # Se lee desde el final por bloques: los logs de la Mac pasan de 100 kB y el de systemd crece sin rotar.
        fh.seek(0, 2)
        pos, chunk, buf = fh.tell(), 64 * 1024, b""
        while pos > 0 and buf.count(b"\n") <= lines:
            step = min(chunk, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
    out["lines"] = buf.decode("utf-8", errors="replace").splitlines()[-lines:]
    return out


def job_runs(days=7):
    """Corridas de `jobs.run` de los últimos `days` días (`data/logs/jobs.jsonl`), la más reciente primero. Una línea
    ilegible se salta: el log lo escriben procesos que pueden morir a medias."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    out = []
    for line in log_tail("jobs", lines=JOB_RUN_LINES)["lines"]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("started_at", "") >= since:
            out.append(row)
    return out[::-1]


def jobs_status(days=7):
    """Cada trabajo del registro con su horario y, de las corridas en `days` días, la última (inicio, resultado,
    duración, memoria), cuántas corrió, cuántas fallaron y el pico de memoria. Sin corridas, los campos van en None."""
    runs = job_runs(days=days)
    out = []
    for e in job_registry.entries():
        mine = [r for r in runs if r.get("key") == e["key"] and r.get("status") != "skipped"]
        last = mine[0] if mine else {}
        rss = [r["max_rss_mb"] for r in mine if r.get("max_rss_mb") is not None]
        out.append({
            "key": e["key"], "area": e["area"], "description": e["description"],
            "schedule": job_registry.describe_schedule(e["schedule"]), "enabled": e["enabled"], "hosts": list(e["hosts"]),
            "timeout_min": e["timeout_min"], "last_started_at": last.get("started_at"), "last_status": last.get("status"),
            "last_duration_s": last.get("duration_s"), "last_max_rss_mb": last.get("max_rss_mb"), "runs": len(mine),
            "failures": sum(1 for r in mine if r.get("status") in ("failed", "timeout")),
            "peak_rss_mb": max(rss) if rss else None,
        })
    return out


def _dir_size(path):
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total


def storage():
    """Tamaño de las bases (`snapshots.db` con su WAL y `app.db`, la de cuentas), del crudo y del respaldo local, y el
    espacio libre del disco de `data/`."""
    db, wal = config.DB_PATH, config.DB_PATH.with_name(config.DB_PATH.name + "-wal")
    usage = shutil.disk_usage(config.DATA_DIR if config.DATA_DIR.exists() else config.ROOT)
    return {
        "db_bytes": db.stat().st_size if db.exists() else 0,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "app_db_bytes": config.APP_DB_PATH.stat().st_size if config.APP_DB_PATH.exists() else 0,
        "raw_bytes": _dir_size(config.RAW_DIR),
        "backups_bytes": _dir_size(config.DATA_DIR / "backups"),
        "disk_total_bytes": usage.total, "disk_free_bytes": usage.free,
        "data_dir": str(config.DATA_DIR),
    }


def deployment():
    """Commit en ejecución (hash corto, fecha y asunto) y la última línea de los logs de despliegue y respaldo.
    Sin git o fuera de un clon, `commit` es None."""
    out = {"commit": None, "commit_at": None, "commit_subject": None, "last_deploy": None, "last_backup": None}
    try:
        show = subprocess.run(["git", "log", "-1", "--format=%h%x1f%cI%x1f%s"], cwd=config.ROOT, capture_output=True,
                              text=True, timeout=5, check=True).stdout.strip()
        out["commit"], out["commit_at"], out["commit_subject"] = show.split("\x1f", 2)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    for key, name in (("last_deploy", "deploy"), ("last_backup", "backup")):
        tail = log_tail(name, lines=1)["lines"]
        out[key] = tail[-1] if tail else None
    return out


def format_report(r):
    lines = [f"salud {r['at']} · últimas {r['hours']} h · {'OK' if r['ok'] else str(len(r['problems'])) + ' problema(s)'}"]
    for chain, c in r["chains"].items():
        if not c:
            lines.append(f"  {chain}: sin datos"); continue
        lines.append(f"  {chain}: última {c['last_at']} ({c['last_age_min']} min, {'ok' if c['last_ok'] else 'FALLÓ'}, {c['last_shows']} funciones); "
                     f"capturas {c['snapshots']} (programadas {c['expected']}, faltan {len(c['missing'])}), fallidas {c['failed']}; "
                     f"ocupación T−60 {c['occupancy_t60']}, post-inicio {c['occupancy_post_start']}; precios 7d {c['prices_7d']}; "
                     f"dulcería 8d: {c['concession_cinemas_8d']} cines, {c['delivery_stores_8d']} tiendas a domicilio"
                     + (f"; calibración semáforo {c['calibration']} de 100 por nivel" if "calibration" in c else "")
                     + (f"; preventa 24h {c['presale_24h']} planos" if "presale_24h" in c else ""))
    for p in r["problems"]:
        lines.append(f"  ! {p}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    conn = store.connect()
    r = check(conn, hours=a.hours)
    conn.close()
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else format_report(r), flush=True)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.LOG_DIR / "health.log", "a", encoding="utf-8") as fh:
        fh.write(format_report(r).replace("\n", " | ") + "\n")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
