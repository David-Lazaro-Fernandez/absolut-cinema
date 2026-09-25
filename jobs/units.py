"""Genera, desde `jobs.registry`, lo que programa los trabajos y la tabla que los documenta.

Uso:
  python3 -m jobs.units write            # reescribe deploy/systemd/ y la tabla de ARCHITECTURE.md
  python3 -m jobs.units check            # sale con 1 si alguno de los dos no coincide con el registro (lo corre pytest)
  python3 -m jobs.units launchd DIR      # plists de la Mac en DIR con la ruta de este clon (no se versionan)
  python3 -m jobs.units timers           # timers de systemd que install.sh y update.sh dejan encendidos

Cada unidad de systemd ejecuta `make job KEY=llave` y no sabe nada más del trabajo. Las unidades generadas viven en
`deploy/systemd/`; `deploy/absolut-cinema-dashboard.service` es un servicio permanente y se escribe a mano.
"""
import argparse
import sys
from pathlib import Path

from scraper import config

from . import registry

SERVER_ROOT = "/opt/absolut-cinema"
SYSTEMD_DIR = config.ROOT / "deploy" / "systemd"
DOC_PATH = config.ROOT / "ARCHITECTURE.md"
DOC_BEGIN, DOC_END = "<!-- jobs:begin -->", "<!-- jobs:end -->"
HEADER = "# Generado por `python3 -m jobs.units write` desde jobs/registry.py; no se edita a mano."
LABEL_PREFIX = "com.absolut-cinema."
# Holgura del tope de systemd sobre el de jobs.run: el runner corta primero y registra la corrida.
SYSTEMD_GRACE_MIN = 5


def unit_name(key, kind):
    return f"absolut-cinema-{key}.{kind}"


def _on_calendar(spec):
    p = registry.parse_schedule(spec)
    day = f"{p['day']:02d}" if p["day"] is not None else "*"
    hour = f"{p['hour']:02d}" if p["hour"] is not None else "*"
    weekday = f"{registry.WEEKDAYS[p['weekday']]} " if p["weekday"] is not None else ""
    return f"{weekday}*-*-{day} {hour}:{p['minute']:02d}:00"


def service(e):
    after = "network-online.target" + (" warp-svc.service privoxy.service" if e["egress"] else "")
    lines = [HEADER, "[Unit]", f"Description=absolut-cinema: {e['description']}", f"After={after}",
             "Wants=network-online.target", "", "[Service]", "Type=oneshot"]
    if e["user"] != "root":
        lines.append(f"User={e['user']}")
    lines += [f"WorkingDirectory={SERVER_ROOT}", "EnvironmentFile=-/etc/absolut-cinema.env",
              f"ExecStart=/usr/bin/make -C {SERVER_ROOT} job KEY={e['key']}",
              f"TimeoutStartSec={e['timeout_min'] + SYSTEMD_GRACE_MIN}min"]
    if e["nice"]:
        lines.append(f"Nice={e['nice']}")
    lines += [f"StandardOutput=append:{SERVER_ROOT}/data/logs/systemd.out",
              f"StandardError=append:{SERVER_ROOT}/data/logs/systemd.out"]
    return "\n".join(lines) + "\n"


def timer(e):
    lines = [HEADER, "[Unit]", f"Description=absolut-cinema: {e['key']}, {registry.describe_schedule(e['schedule'])}"
             + ("" if e["enabled"] else " (apagado: se enciende a mano)"), "", "[Timer]"]
    lines += [f"OnCalendar={_on_calendar(s)}" for s in e["schedule"]]
    lines.append(f"Persistent={'true' if e['catch_up'] else 'false'}")
    if e["jitter_min"]:
        lines.append(f"RandomizedDelaySec={e['jitter_min']}min")
    lines += ["AccuracySec=30s", "", "[Install]", "WantedBy=timers.target"]
    return "\n".join(lines) + "\n"


def systemd_files():
    """{nombre de archivo: contenido} de todas las unidades del servidor."""
    out = {}
    for e in registry.entries(host="server"):
        out[unit_name(e["key"], "service")] = service(e)
        out[unit_name(e["key"], "timer")] = timer(e)
    return out


def plist(e, root):
    intervals = []
    for spec in e["schedule"]:
        p = registry.parse_schedule(spec)
        fields = []
        if p["weekday"] is not None:
            fields.append(("Weekday", (p["weekday"] + 1) % 7))     # launchd: 0 = domingo
        if p["day"] is not None:
            fields.append(("Day", p["day"]))
        if p["hour"] is not None:
            fields.append(("Hour", p["hour"]))
        fields.append(("Minute", p["minute"]))
        intervals.append("    <dict>" + "".join(f"<key>{k}</key><integer>{v}</integer>" for k, v in fields) + "</dict>")
    log = f"{root}/data/logs/launchd.out"
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">', "<dict>",
        f"  <key>Label</key><string>{LABEL_PREFIX}{e['key']}</string>",
        "  <key>ProgramArguments</key>", "  <array>",
        *(f"    <string>{a}</string>" for a in ("/usr/bin/make", "-C", root, "job", f"KEY={e['key']}")),
        "  </array>", "  <key>StartCalendarInterval</key>", "  <array>", *intervals, "  </array>",
        f"  <key>WorkingDirectory</key><string>{root}</string>",
        f"  <key>StandardOutPath</key><string>{log}</string>",
        f"  <key>StandardErrorPath</key><string>{log}</string>",
        "</dict>", "</plist>", ""])


def doc_table():
    """La tabla de trabajos programados para ARCHITECTURE.md."""
    rows = ["| Llave (`make job KEY=…`) | Área | Qué hace | Cuándo (CDMX) | Tope | Dónde | Escribe |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for e in registry.entries():
        when = registry.describe_schedule(e["schedule"]) + ("" if e["enabled"] else " · **apagado**")
        hosts = " y ".join({"server": "servidor", "mac": "Mac"}[h] for h in e["hosts"])
        extra = f"; {e['retries']} reintento a los {e['retry_delay_s'] // 60} min" if e["retries"] else ""
        rows.append(f"| `{e['key']}` | {e['area']} | {e['description']} | {when} | {e['timeout_min']} min{extra} | "
                    f"{hosts} | {', '.join(f'`{w}`' for w in e['writes'])} |")
    return "\n".join(rows)


def _doc_with_table(text):
    head, sep, rest = text.partition(DOC_BEGIN)
    _, sep2, tail = rest.partition(DOC_END)
    if not sep or not sep2:
        raise registry.RegistryError(f"{DOC_PATH.name} no tiene los marcadores {DOC_BEGIN} / {DOC_END}")
    return f"{head}{DOC_BEGIN}\n{doc_table()}\n{DOC_END}{tail}"


def check():
    """Diferencias entre lo generado y lo versionado; lista vacía si todo coincide."""
    problems = []
    want = systemd_files()
    have = {p.name: p.read_text(encoding="utf-8") for p in SYSTEMD_DIR.glob("*") if p.is_file()} if SYSTEMD_DIR.exists() else {}
    for name in sorted(set(want) | set(have)):
        if want.get(name) != have.get(name):
            problems.append(f"deploy/systemd/{name}: " + ("sobra" if name not in want else "falta" if name not in have else "difiere"))
    doc = DOC_PATH.read_text(encoding="utf-8")
    if _doc_with_table(doc) != doc:
        problems.append(f"{DOC_PATH.name}: la tabla de trabajos no coincide con el registro")
    return problems


def write():
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    want = systemd_files()
    for p in SYSTEMD_DIR.glob("*"):
        if p.name not in want:
            p.unlink()
    for name, text in want.items():
        (SYSTEMD_DIR / name).write_text(text, encoding="utf-8")
    DOC_PATH.write_text(_doc_with_table(DOC_PATH.read_text(encoding="utf-8")), encoding="utf-8")


def write_launchd(out_dir, root):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob(f"{LABEL_PREFIX}*.plist"):
        p.unlink()
    for e in registry.entries(host="mac"):
        if e["enabled"]:
            (out_dir / f"{LABEL_PREFIX}{e['key']}.plist").write_text(plist(e, str(root)), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("write")
    sub.add_parser("check")
    lp = sub.add_parser("launchd")
    lp.add_argument("out_dir")
    lp.add_argument("--root", default=str(config.ROOT))
    sub.add_parser("timers")
    a = ap.parse_args(argv)
    if a.cmd == "write":
        write()
    elif a.cmd == "check":
        problems = check()
        for p in problems:
            print(p)
        return 1 if problems else 0
    elif a.cmd == "launchd":
        write_launchd(a.out_dir, a.root)
    else:
        print("\n".join(unit_name(e["key"], "timer") for e in registry.entries(host="server") if e["enabled"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
