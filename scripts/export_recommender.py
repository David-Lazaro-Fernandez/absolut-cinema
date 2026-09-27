"""Exporta el catálogo del recomendador público ("¿A dónde ir?" de la landing, `marketing/app/a-donde-ir/`) a un JSON
compacto que el navegador descarga y filtra sin servidor.

Uso:
  python3 scripts/export_recommender.py                 # CDMX, Guadalajara y Monterrey, de hoy a 6 días,
                                                        # a marketing/public/data/a-donde-ir.json
  python3 scripts/export_recommender.py --plazas cdmx --days 3 --out /tmp/catalogo.json

Los precios salen de `analytics.recommend_catalog`, la misma lógica del recomendador del dashboard (boleto por tipo de
persona de la lectura más reciente por cine, formato y tipo de día; dulcería del menú en sala). El navegador solo suma
y filtra. Formato (versión 1), pensado para pesar poco: los textos repetidos van una vez en listas y las filas los
nombran por índice. Las plazas van juntas en un solo archivo: el navegador elige por distancia al punto de partida.
  generated_at, plazas [[clave, etiqueta, lat, lng, [oeste, sur, este, norte]]]   (centro y caja de sus cines),
  dates [[fecha, tipo de día]], chains [etiqueta], formats [clave], languages [clave],
  titles [título], packages {paquete: [[producto, personas que cubre]]},
  cinemas [[cadena, nombre, lat, lng, {producto: precio}]],
  prices {"cine|formato|tipo de día": [adulto, niño, adulto mayor, fecha de la lectura]},
  shows [[cine, fecha, título, formato, idioma, [minutos desde medianoche, …]]]   (hora local de la plaza)
Solo librería estándar; abre la base en solo lectura como el resto de `analytics/`.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analytics  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "marketing" / "public" / "data" / "a-donde-ir.json"
FORMAT_VERSION = 2
AREA_MARGIN_DEG = 0.05                          # ~5 km alrededor del cine más alejado de cada plaza


def _index(values):
    order = list(dict.fromkeys(values))
    return order, {v: i for i, v in enumerate(order)}


def merge(catalogs):
    """Varios catálogos de `analytics.recommend_catalog` (uno por plaza) en uno, con las funciones en su orden."""
    shows = sorted((s for c in catalogs.values() for s in c["shows"]),
                   key=lambda s: (s["date"], s["datetime_local"], s["chain"], s["cinema_id"], s["title_norm"]))
    return {"cinemas": [x for c in catalogs.values() for x in c["cinemas"]],
            "prices": [x for c in catalogs.values() for x in c["prices"]],
            "shows": shows, "packages": next(iter(catalogs.values()))["packages"]}


def area(plaza, cinemas):
    """[clave, etiqueta, lat, lng, [oeste, sur, este, norte]]: el centro de los cines de la plaza y su caja con margen."""
    lats, lngs = [c["lat"] for c in cinemas], [c["lng"] for c in cinemas]
    m = AREA_MARGIN_DEG
    return [plaza, analytics.labels.PLAZA_LABEL.get(plaza, plaza), round(sum(lats) / len(lats), 4), round(sum(lngs) / len(lngs), 4),
            [round(min(lngs) - m, 2), round(min(lats) - m, 2), round(max(lngs) + m, 2), round(max(lats) + m, 2)]]


def compact(catalog, areas):
    """El catálogo de `analytics.recommend_catalog` (o de `merge`) en el formato compacto descrito arriba."""
    cinemas = catalog["cinemas"]
    cinema_ix = {(c["chain"], c["cinema_id"]): i for i, c in enumerate(cinemas)}
    chains, chain_ix = _index(c["chain_label"] for c in cinemas)
    shows = catalog["shows"]
    dates, date_ix = _index(s["date"] for s in shows)
    day_type = {s["date"]: s["day_type"] for s in shows}
    formats, format_ix = _index(sorted({s["format_bucket"] for s in shows} | {p["format_bucket"] for p in catalog["prices"]}))
    languages, language_ix = _index(sorted({s["language"] for s in shows}))
    titles, title_ix = _index(s["title"] for s in sorted(shows, key=lambda s: (s["title_norm"], s["title"])))
    # Una película se muestra con un solo título aunque cada cadena la escriba distinto.
    title_of = {}
    for s in shows:
        title_of.setdefault(s["title_norm"], s["title"])
    groups = {}
    for s in shows:
        key = (cinema_ix[(s["chain"], s["cinema_id"])], date_ix[s["date"]], title_ix[title_of[s["title_norm"]]],
               format_ix[s["format_bucket"]], language_ix[s["language"]])
        hh, mm = int(s["datetime_local"][11:13]), int(s["datetime_local"][14:16])
        groups.setdefault(key, []).append(hh * 60 + mm)
    return {
        "version": FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plazas": areas,
        "dates": [[d, day_type[d]] for d in dates],
        "chains": chains, "formats": formats, "languages": languages,
        "titles": titles,
        "packages": {k: [list(item) for item in v] for k, v in catalog["packages"].items()},
        "cinemas": [[chain_ix[c["chain_label"]], c["cinema_name"], round(c["lat"], 5), round(c["lng"], 5), c["snacks"]]
                    for c in cinemas],
        "prices": {f"{cinema_ix[(p['chain'], p['cinema_id'])]}|{format_ix[p['format_bucket']]}|{p['day_type']}":
                   [p["adult"], p["child"], p["senior"], p["sampled_at"][:10]] for p in catalog["prices"]},
        "shows": [[*key, sorted(times)] for key, times in sorted(groups.items())],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plazas", default="cdmx,gdl,mty", help="claves de scraper/plazas.py separadas por coma")
    ap.add_argument("--days", type=int, default=7, help="días de cartelera desde hoy (las cadenas publican hasta el miércoles)")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    d0 = analytics.today()
    d1 = (date.fromisoformat(d0) + timedelta(days=a.days - 1)).isoformat()
    conn = analytics.connect()
    try:
        catalogs = {p: analytics.recommend_catalog(conn, d0, d1, plaza=p) for p in a.plazas.split(",")}
        catalogs = {p: c for p, c in catalogs.items() if c["cinemas"]}
        data = compact(merge(catalogs), [area(p, c["cinemas"]) for p, c in catalogs.items()])
    finally:
        conn.close()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{a.out}: {', '.join(p[1] for p in data['plazas'])}; {len(data['cinemas'])} cines, {sum(len(s[-1]) for s in data['shows'])} funciones, "
          f"{len(data['prices'])} precios, {a.out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
