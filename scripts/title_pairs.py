"""Candidatos para la tabla de equivalencias de títulos entre cadenas (scraper/title_pairs.csv).

Uso:
  python3 scripts/title_pairs.py                         # lista los pares por revisar, del más parecido al menos
  python3 scripts/title_pairs.py --accept A B [--note …]  # A y B son la misma película (title_norm de cada cadena)
  python3 scripts/title_pairs.py --reject A B [--note …]  # no lo son: deja de proponerse y los exime de las reglas

Lee `current_showtime` de data/snapshots.db en solo lectura y propone con `scraper.titles.candidates`: parecido de
texto y números iguales, con la duración y la distribuidora al lado como evidencia (no como regla: "Transformers: La
película" dura 84 min en Cinemex y 96 en la edición de aniversario de Cinépolis). Nada se une sin `--accept`. Se corre
cuando `scraper.health` avisa que hay pares por revisar. Solo librería estándar.
"""
import argparse
import csv
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import config, titles  # noqa: E402


def load_titles(conn, chain):
    """{title_norm: {title, duration_min, distributor, shows}} de la cartelera vigente de una cadena."""
    return {r[0]: {"title": r[1], "duration_min": r[2], "distributor": r[3], "shows": r[4]} for r in conn.execute("""
        SELECT title_norm, MAX(movie_title), MAX(duration_min), MAX(distributor), COUNT(*)
        FROM current_showtime WHERE chain = ? AND title_norm <> '' GROUP BY title_norm""", (chain,))}


def pending(conn):
    return titles.candidates(load_titles(conn, "cinemex"), load_titles(conn, "cinepolis"))


def decide(a, b, decision, note):
    new = not titles.PAIRS_PATH.exists()
    with open(titles.PAIRS_PATH, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["title_norm_a", "title_norm_b", "decision", "note", "decided_at"])
        w.writerow([a, b, decision, note, date.today().isoformat()])
    print(f"{decision}: {a} · {b} → {titles.PAIRS_PATH.name}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--accept", nargs=2, metavar=("A", "B"), help="misma película")
    group.add_argument("--reject", nargs=2, metavar=("A", "B"), help="películas distintas")
    ap.add_argument("--note", default="", help="por qué, para quien lea la tabla después")
    a = ap.parse_args(argv)
    if a.accept or a.reject:
        decide(*(a.accept or a.reject), "same" if a.accept else "different", a.note)
        return 0
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    found = pending(conn)
    if not found:
        print("Sin pares por revisar.")
    for c in found:
        print(f"{c['ratio']:.2f}  Cinemex  «{c['title_a']}» ({c['duration_a'] or '—'} min, {c['distributor_a'] or '—'}, {c['shows_a']} funciones)\n"
              f"      Cinépolis «{c['title_b']}» ({c['duration_b'] or '—'} min, {c['distributor_b'] or '—'}, {c['shows_b']} funciones)\n"
              f"      --accept \"{c['a']}\" \"{c['b']}\"   |   --reject \"{c['a']}\" \"{c['b']}\"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
