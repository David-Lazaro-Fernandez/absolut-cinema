"""Salud de la captura: un reporte diario que dice si la serie está completa y si el muestreo avanza.

Uso: python3 -m scraper.health [--hours 24] [--json]
Sale con código 1 si hay algún problema, para que el timer/launchd lo marque como fallido. Escribe una
línea por corrida en data/logs/health.log y el detalle en stdout. Solo librería estándar.

Revisa, para cada cadena y la ventana dada:
  - última captura: edad y si terminó bien (umbral: 45 min, el mismo que el aviso del dashboard);
  - snapshots esperados (uno cada 15 min) vs obtenidos, cuántos fallaron y huecos > 30 min
    (la Mac dormida o sin red deja huecos; en el servidor no debería haber);
  - muestras de ocupación a T−60 y post-inicio, y precios de los últimos 7 días.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import config, store

MAX_AGE_MIN = 45        # mismo umbral que el aviso del dashboard
GAP_MIN = 30            # dos snapshots seguidos perdidos
CHAINS = ("cinemex", "cinepolis")


def _dt(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def check(conn, hours=24, now=None):
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
    expected = hours * 4
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
        c["snapshots"], c["expected"], c["failed"] = len(rows), expected, sum(1 for r in rows if not r["ok"])
        gaps, prev = [], None
        for r in rows:
            t = _dt(r["taken_at"])
            if prev and (t - prev).total_seconds() / 60 > GAP_MIN:
                gaps.append((prev.isoformat(timespec="minutes"), round((t - prev).total_seconds() / 60)))
            prev = t
        c["gaps"] = gaps
        if c["failed"]:
            report["problems"].append(f"{chain}: {c['failed']} capturas fallidas en {hours} h")
        if gaps:
            report["problems"].append(f"{chain}: {len(gaps)} hueco(s) > {GAP_MIN} min, el mayor de {max(g[1] for g in gaps)} min")
        occ = conn.execute("""SELECT SUM(minutes_to_start >= 0) pre, SUM(minutes_to_start < 0) post
                              FROM occupancy_sample WHERE chain = ? AND sampled_at >= ?""", (chain, since)).fetchone()
        c["occupancy_t60"], c["occupancy_post_start"] = occ["pre"] or 0, occ["post"] or 0
        c["prices_7d"] = conn.execute("SELECT COUNT(*) FROM price_sample WHERE chain = ? AND sampled_at >= ?",
                                      (chain, (now - timedelta(days=7)).isoformat(timespec="seconds"))).fetchone()[0]
        report["chains"][chain] = c
    # el muestreo de planos hoy solo corre para Cinépolis; si no hay ninguna muestra en la ventana, algo se detuvo
    cp = report["chains"].get("cinepolis", {})
    if cp and cp.get("snapshots") and not cp.get("occupancy_t60") and not cp.get("occupancy_post_start"):
        report["problems"].append("cinepolis: cero muestras de ocupación en la ventana (¿se cayó el pase de planos?)")
    report["ok"] = not report["problems"]
    return report


def format_report(r):
    lines = [f"salud {r['at']} · últimas {r['hours']} h · {'OK' if r['ok'] else str(len(r['problems'])) + ' problema(s)'}"]
    for chain, c in r["chains"].items():
        if not c:
            lines.append(f"  {chain}: sin datos"); continue
        lines.append(f"  {chain}: última {c['last_at']} ({c['last_age_min']} min, {'ok' if c['last_ok'] else 'FALLÓ'}, {c['last_shows']} funciones); "
                     f"snapshots {c['snapshots']}/{c['expected']}, fallidos {c['failed']}, huecos {len(c['gaps'])}; "
                     f"ocupación T−60 {c['occupancy_t60']}, post-inicio {c['occupancy_post_start']}; precios 7d {c['prices_7d']}")
        for start, mins in c["gaps"][:5]:
            lines.append(f"    hueco desde {start} de {mins} min")
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
