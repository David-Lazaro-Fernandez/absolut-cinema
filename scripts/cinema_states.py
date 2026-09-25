"""Asigna a cada cine su estado (clave de entidad de INEGI) por coordenadas y escribe scraper/cinema_states.csv.

Uso: python3 scripts/cinema_states.py POLIGONOS.geojson
POLIGONOS es el ADM1 de México de geoBoundaries (fuente INEGI 2020, CC BY 3.0 IGO), a resolución completa:
  https://www.geoboundaries.org/api/current/gbOpen/MEX/ADM1/  → gjDownloadURL
No se versiona (36 MB). Se corre una vez y de nuevo cuando `scraper.health` lista cines sin estado.

Lee la dimensión `cinema` de data/snapshots.db en solo lectura. Un cine dentro de un polígono toma ese estado
(`method=polygon`); uno que cae fuera de todos (coordenadas en la costa o un punto mal capturado) toma el estado del
borde más cercano (`method=nearest`, con la distancia en km) y se imprime para revisarlo. Una longitud positiva (Cinépolis publica
algunas sin signo) se corrige y queda como `method=lng_sign`. Solo librería estándar.
"""
import csv
import json
import math
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import config, states  # noqa: E402

# Nombres de geoBoundaries que no coinciden con los de `states.STATES` (su ISO de CDMX viene mal: MX-MEX).
_ALIASES = {"distrito federal": "09", "mexico": "15", "coahuila de zaragoza": "05", "michoacan de ocampo": "16",
            "queretaro de arteaga": "22", "veracruz de ignacio de la llave": "30"}
NEAREST_WARN_KM = 2.0


def _norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _code(name):
    by_name = {_norm(v): k for k, v in states.STATES.items()}
    return _ALIASES.get(_norm(name)) or by_name[_norm(name)]


def load_polygons(path):
    """[(clave, [anillos], bbox)] con cada polígono de cada estado; anillos en (lng, lat), el primero es el exterior."""
    out = []
    for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"]:
        code = _code(f["properties"]["shapeName"])
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for rings in polys:
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            out.append((code, rings, (min(xs), min(ys), max(xs), max(ys))))
    codes = {c for c, _, _ in out}
    if codes != set(states.STATES):
        raise SystemExit(f"faltan estados en los polígonos: {sorted(set(states.STATES) - codes)}")
    return out


def _inside(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _segment_km(x, y, ax, ay, bx, by):
    # Distancia aproximada punto–segmento: proyección equirectangular local, suficiente a escala de pocos km.
    kx, ky = 111.32 * math.cos(math.radians(y)), 110.57
    px, py, ax, ay, bx, by = x * kx, y * ky, ax * kx, ay * ky, bx * kx, by * ky
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def locate(lng, lat, polygons):
    """(clave, método, km): dentro de un polígono, o el estado del borde más cercano."""
    for code, rings, (x0, y0, x1, y1) in polygons:
        if x0 <= lng <= x1 and y0 <= lat <= y1 and _inside(lng, lat, rings[0]) \
                and not any(_inside(lng, lat, hole) for hole in rings[1:]):
            return code, "polygon", 0.0
    best = (None, math.inf)
    for code, rings, _ in polygons:
        ring = rings[0]
        for i in range(len(ring) - 1):
            d = _segment_km(lng, lat, ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1])
            if d < best[1]:
                best = (code, d)
    return best[0], "nearest", round(best[1], 2)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        raise SystemExit(__doc__)
    polygons = load_polygons(argv[0])
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cinemas = conn.execute("SELECT chain, cinema_id, name, lat, lng, city_id, state_id FROM cinema ORDER BY chain, cinema_id").fetchall()
    rows, no_coords = [], []
    for c in cinemas:
        if c["lat"] is None or c["lng"] is None:
            no_coords.append(c)
            continue
        code, method, km = locate(float(c["lng"]), float(c["lat"]), polygons)
        if method == "nearest" and km > NEAREST_WARN_KM and float(c["lng"]) > 0:
            # Cinépolis publica algunas longitudes sin signo (Diana Acapulco: 99.873); todo México es longitud oeste.
            code, method, km = locate(-float(c["lng"]), float(c["lat"]), polygons)
            method = "lng_sign" if method == "polygon" else method
        rows.append({"chain": c["chain"], "cinema_id": c["cinema_id"], "state_code": code, "city_id": c["city_id"],
                     "method": method, "distance_km": km, "name": c["name"], "api_state_id": c["state_id"]})
        if method != "polygon":
            flag = "  REVISAR" if km > NEAREST_WARN_KM else ""
            print(f"fuera de polígono: {c['chain']} {c['cinema_id']} ({c['name']}) → {states.STATES[code]} a {km} km{flag}")
    with open(states.MAPPING_PATH, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["chain", "cinema_id", "state_code", "city_id", "method", "distance_km", "name"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} cines con estado en {states.MAPPING_PATH.name}; {len(no_coords)} sin coordenadas: "
          + ", ".join(f"{c['chain']} {c['cinema_id']}" for c in no_coords))

    # Verificación contra la geografía de cada API: estados de INEGI por estado de Cinemex y ciudades de Cinépolis que
    # cruzan una frontera estatal.
    by_api_state = defaultdict(Counter)
    by_city = defaultdict(Counter)
    for r in rows:
        if r["chain"] == "cinemex":
            by_api_state[r["api_state_id"]][r["state_code"]] += 1
        else:
            by_city[r["city_id"]][r["state_code"]] += 1
    print("\nCinemex, estado de la API → estados INEGI:")
    for sid, cnt in sorted(by_api_state.items(), key=lambda kv: int(kv[0] or 0)):
        print(f"  {sid}: " + ", ".join(f"{states.STATES[k]} {v}" for k, v in cnt.most_common()))
    print("\nCinépolis, ciudades con cines en más de un estado:")
    for city, cnt in sorted(by_city.items()):
        if len(cnt) > 1:
            print(f"  {city}: " + ", ".join(f"{states.STATES[k]} {v}" for k, v in cnt.most_common()))


if __name__ == "__main__":
    main()
