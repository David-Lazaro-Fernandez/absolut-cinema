"""Salud de la captura: un reporte diario que dice si la serie está completa y si el muestreo avanza.

Uso: python3 -m scraper.health [--hours 24] [--json]
Sale con código 1 si hay algún problema, para que el timer/launchd lo marque como fallido. Escribe una
línea por corrida en data/logs/health.log y el detalle en stdout. Solo librería estándar.

Revisa, para cada cadena y la ventana dada:
  - última captura: edad y si terminó bien (umbral MAX_AGE_MIN, el mismo que el aviso del dashboard; la
    cartelera se captura a las horas de `config.SNAPSHOT_HOURS`, así que el hueco normal nocturno es de 11 h);
  - capturas programadas dentro de la ventana que no tienen un snapshot bueno a ±SLOT_TOLERANCE_MIN
    (la Mac dormida o sin red las pierde; en el servidor no debería faltar ninguna), y cuántas fallaron;
  - muestras de ocupación a T−60 y post-inicio, precios de 7 días, y que los pases semanales de dulcería
    (menú de Cinépolis, tiendas a domicilio) no lleven más de 8 días sin renovarse.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, sample, store

MAX_AGE_MIN = 12 * 60        # tres capturas al día: el hueco normal más largo (20:30 → 07:30) es de 11 h
SLOT_TOLERANCE_MIN = 30      # una captura programada cuenta si hay snapshot bueno a ±30 min
CHAINS = ("cinemex", "cinepolis")


def _dt(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def scheduled_captures(now, hours):
    """Instantes UTC de las capturas programadas (`config.SNAPSHOT_HOURS`, hora local de la plaza) que caen en
    la ventana [now − hours, now − tolerancia]: las que ya deberían existir."""
    tz = ZoneInfo(config.PILOT_TIMEZONE)
    start, latest = now - timedelta(hours=hours), now - timedelta(minutes=SLOT_TOLERANCE_MIN)
    day, out = start.astimezone(tz).date(), []
    while datetime(day.year, day.month, day.day, tzinfo=tz) <= latest:
        for hm in config.SNAPSHOT_HOURS:
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
        last = conn.execute("SELECT taken_at, finished_at, ok, n_shows, error FROM snapshot WHERE chain = ? ORDER BY id DESC LIMIT 1",
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
        if chain == "cinemex":
            # Calibración del semáforo: se hace por chunks (make calibrate-cinemex); aquí el avance por nivel.
            have = sample.calibration_progress(conn, chain)
            c["calibration"] = {lvl: have.get(lvl, 0) for lvl in sample.CALIBRATION_LEVELS}
        report["chains"][chain] = c
    # el muestreo de planos hoy solo corre para Cinépolis; si no hay ninguna muestra en la ventana, algo se detuvo
    cp = report["chains"].get("cinepolis", {})
    if cp and cp.get("snapshots") and not cp.get("occupancy_post_start"):
        report["problems"].append("cinepolis: cero planos post-inicio en la ventana (¿se cayó el pase de butacas?)")
    report["ok"] = not report["problems"]
    return report


def format_report(r):
    lines = [f"salud {r['at']} · últimas {r['hours']} h · {'OK' if r['ok'] else str(len(r['problems'])) + ' problema(s)'}"]
    for chain, c in r["chains"].items():
        if not c:
            lines.append(f"  {chain}: sin datos"); continue
        lines.append(f"  {chain}: última {c['last_at']} ({c['last_age_min']} min, {'ok' if c['last_ok'] else 'FALLÓ'}, {c['last_shows']} funciones); "
                     f"capturas {c['snapshots']} (programadas {c['expected']}, faltan {len(c['missing'])}), fallidas {c['failed']}; "
                     f"ocupación T−60 {c['occupancy_t60']}, post-inicio {c['occupancy_post_start']}; precios 7d {c['prices_7d']}; "
                     f"dulcería 8d: {c['concession_cinemas_8d']} cines, {c['delivery_stores_8d']} tiendas a domicilio"
                     + (f"; calibración semáforo {c['calibration']} de 100 por nivel" if "calibration" in c else ""))
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
