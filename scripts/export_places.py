"""Exporta el índice de lugares de CDMX, Guadalajara y Monterrey para las sugerencias instantáneas de "¿A dónde ir?" de
la landing (`marketing/public/data/lugares.json`): colonias, alcaldías, ciudades, estaciones de transporte, plazas
comerciales y universidades, con coordenadas, desde OpenStreetMap (Overpass API).

Uso:
  python3 scripts/export_places.py                    # a marketing/public/data/lugares.json
  python3 scripts/export_places.py --out /tmp/lugares.json

Es una consulta de unos 6 mil lugares (2026-09-27), por eso corre al construir el sitio y no en cada visita. Si
Overpass no responde, el script conserva el archivo anterior y sale con 0. Sin archivo, la página sugiere solo con el
geocodificador en línea. Los datos son de OpenStreetMap (ODbL); el sitio da el crédito. Formato (versión 1):
  generated_at, source, kinds [etiqueta], places [[nombre, tipo, lat, lng]]
`kinds` está en orden de prioridad. Con la misma coincidencia, una alcaldía va antes que una universidad.
Solo librería estándar.
"""
import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "marketing" / "public" / "data" / "lugares.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "absolut-cinema/1.0 (export de lugares para la landing)"
# Caja de cada plaza en el orden de Overpass (sur, oeste, norte, este). Es un poco más grande que la zona de sus cines.
AREAS = {"cdmx": (19.05, -99.40, 19.90, -98.80),
         "gdl": (20.45, -103.55, 20.80, -103.18),
         "mty": (25.35, -100.55, 25.97, -100.03)}
TIMEOUT_S = 120
SAME_PLACE_M = 400                              # a esta distancia o menos, mismo nombre y tipo es un solo lugar
KINDS = ["Alcaldía", "Ciudad", "Colonia", "Metro", "Metrobús", "Tren Ligero", "Cablebús", "Mexibús", "Mexicable",
         "Mi Macro", "Metrorrey", "Ecovía", "Estación", "Pueblo", "Localidad", "Plaza comercial", "Universidad"]
_QUERY = """[out:json][timeout:{timeout}];
(
{parts}
);
out tags center;"""
_PART = """  nwr["place"~"^(city|suburb|neighbourhood|quarter|borough|city_block|village|town)$"]["name"]({bbox});
  nwr["public_transport"="station"]["name"]({bbox});
  nwr["shop"="mall"]["name"]({bbox});
  nwr["amenity"="university"]["name"]({bbox});"""


def kind_of(tags):
    """Etiqueta de `KINDS` para un elemento de OSM, o None si no interesa."""
    place = tags.get("place")
    if place == "borough":
        return "Alcaldía"
    if place == "city":
        return "Ciudad"
    if place in ("suburb", "neighbourhood", "quarter", "city_block"):
        return "Colonia"
    if place == "village":
        return "Pueblo"
    if place == "town":
        return "Localidad"
    if tags.get("shop") == "mall":
        return "Plaza comercial"
    if tags.get("amenity") == "university":
        return "Universidad"
    if tags.get("public_transport") == "station":
        text = " ".join(tags.get(k, "") for k in ("network", "operator", "station", "railway")).lower()
        for word, kind in (("metrobús", "Metrobús"), ("metrobus", "Metrobús"), ("mexibús", "Mexibús"), ("mexibus", "Mexibús"),
                           ("cablebús", "Cablebús"), ("cablebus", "Cablebús"), ("mexicable", "Mexicable"),
                           ("mi macro", "Mi Macro"), ("macrobús", "Mi Macro"), ("macrobus", "Mi Macro"),
                           ("metrorrey", "Metrorrey"), ("ecovía", "Ecovía"), ("ecovia", "Ecovía"),
                           ("light_rail", "Tren Ligero"), ("tren ligero", "Tren Ligero"), ("subway", "Metro"), ("stc", "Metro")):
            if word in text:
                return kind
        return "Estación"
    return None


def _meters(a, b):
    dlat = (a[0] - b[0]) * 111_320
    dlng = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlng)


def places(elements):
    """[[nombre, tipo, lat, lng]] sin repetidos (una estación trae nodo, andenes y edificio con el mismo nombre)."""
    kind_ix = {k: i for i, k in enumerate(KINDS)}
    kept = {}
    for e in elements:
        tags = e.get("tags", {})
        kind = kind_of(tags)
        where = (e["lat"], e["lon"]) if "lat" in e else ((e["center"]["lat"], e["center"]["lon"]) if "center" in e else None)
        name = (tags.get("name") or "").strip()
        if not kind or not where or not name:
            continue
        same = kept.setdefault((name.lower(), kind), {"name": name, "points": []})["points"]
        if all(_meters(where, p) > SAME_PLACE_M for p in same):
            same.append(where)
    out = [[entry["name"], kind_ix[kind], round(lat, 5), round(lng, 5)]
           for (_, kind), entry in kept.items() for lat, lng in entry["points"]]
    return sorted(out, key=lambda p: (p[1], p[0], p[2], p[3]))


def fetch():
    parts = "\n".join(_PART.format(bbox=",".join(str(v) for v in box)) for box in AREAS.values())
    body = urllib.parse.urlencode({"data": _QUERY.format(timeout=TIMEOUT_S, parts=parts)}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S + 30) as res:
        return json.load(res)["elements"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    try:
        found = places(fetch())
    except (OSError, ValueError, KeyError) as e:
        kept = "se conserva el anterior" if a.out.exists() else "la página sugerirá solo en línea"
        print(f"Overpass no respondió ({e}); {kept}.", file=sys.stderr)
        return 0
    data = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "© OpenStreetMap (ODbL)", "kinds": KINDS, "places": found}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{a.out}: {len(found)} lugares, {a.out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
