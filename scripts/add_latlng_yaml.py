"""Añade lat/lng a cada cine de cinepolis_mx_cines.yaml consultando la API de locations (una llamada por ciudad).

Uso: python3 scripts/add_latlng_yaml.py
Edita el archivo en sitio de forma textual (sin PyYAML) y es idempotente.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import cinepolis  # noqa: E402

YAML = Path(__file__).resolve().parent.parent / "cinepolis_mx_cines.yaml"


def main():
    lines = YAML.read_text(encoding="utf-8").splitlines()
    out, city_id, coords = [], None, {}
    added = missing = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m_city = re.match(r"^    id: (\S+)\s*$", line)
        if m_city:
            city_id = m_city.group(1)
            coords = {c["id"]: c for c in cinepolis.list_cinemas(city_id)}
            print(f"{city_id}: {len(coords)} cines", flush=True)
        m_slug = re.match(r"^        slug: (\S+)\s*$", line)
        out.append(line)
        if m_slug:
            slug = m_slug.group(1)
            # copiar el resto del bloque del cine (vista_id, timezone, lat, lng ya existentes)
            j = i + 1
            block = []
            while j < len(lines) and re.match(r"^        \w", lines[j]):
                block.append(lines[j])
                j += 1
            block = [b for b in block if not re.match(r"^        (lat|lng):", b)]
            c = coords.get(slug)
            if c and c.get("lat") is not None:
                block += [f"        lat: {c['lat']}", f"        lng: {c['lng']}"]
                added += 1
            else:
                missing += 1
                print(f"  sin coordenadas: {slug}", flush=True)
            out.extend(block)
            i = j
            continue
        i += 1
    text = "\n".join(out) + "\n"
    text = re.sub(r"^# Cines Cinépolis México\..*$",
                  "# Cines Cinépolis México. El campo `slug` es el valor de ?cinema= en https://cinepolis.com/mx. lat/lng vienen de la API de locations.",
                  text, count=1, flags=re.M)
    YAML.write_text(text, encoding="utf-8")
    print(f"listo: {added} cines con lat/lng, {missing} sin coordenadas")


if __name__ == "__main__":
    main()
