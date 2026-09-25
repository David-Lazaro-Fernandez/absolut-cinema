"""Cliente de la API GraphQL de Cinépolis y snapshot de un conjunto de ciudades (por defecto, todas)."""
import json
from collections import Counter
from datetime import datetime, timezone

from . import config, states, units
from .http import ApiError, request_json

HEADERS = {
    "x-apikey": config.CINEPOLIS_API_KEY,
    "country-id": config.CINEPOLIS_COUNTRY,
    "language": "ES",
}

CITIES_QUERY = """
query Cities($country: String!) {
  cities(country_id: $country) {
    edges { node { id name timezone lat lng } }
  }
}"""

CINEMAS_QUERY = """
query Cinemas($country: String!, $city: String!) {
  cinemas(country_id: $country, city_id: $city) {
    edges { node { id cityId name vistaId timezone businessType lat lng } }
  }
}"""

MOVIES_QUERY = """
query Movies($countryId: String!, $category: String, $cinemas: String, $after: String, $limit: Int) {
  movies(countryId: $countryId, category: $category, cinemas: $cinemas, after: $after, limit: $limit) {
    pageInfo { endCursor hasNextPage }
    edges { node {
      id name originalName distributor rating genre length releaseDate languages formats
    } }
  }
}"""

BILLBOARD_QUERY = """
query Billboard($countryId: String!, $movieId: String!, $cinemas: String!, $timezone: String) {
  billboard(countryId: $countryId, movieId: $movieId, cinemas: $cinemas, timezone: $timezone) {
    dates
    schedules { cinemaId cityId movieId
      dates { date
        languages { language displayLanguage
          showtimes {
            sessionId datetime screen availability isAllocatedSeating
            format { name } experience { name }
          } } } } } }"""


def gql(url, query, variables, stats=None):
    data = request_json(url, method="POST", headers=HEADERS, body={"query": query, "variables": variables})
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    if data.get("errors"):
        raise ApiError("GraphQL: " + json.dumps(data["errors"], ensure_ascii=False)[:500])
    return data["data"]


def list_cities(stats=None):
    """Ciudades del país: [{id, name, timezone, lat, lng}] (154 el 2026-09-11)."""
    data = gql(config.CINEPOLIS_LOCATIONS_URL, CITIES_QUERY, {"country": config.CINEPOLIS_COUNTRY}, stats)
    return [e["node"] for e in data["cities"]["edges"]]


def list_cinemas(city_id, stats=None):
    """Cines de una ciudad, con `cityId` y `timezone`. La API no tiene listado nacional: exige la ciudad."""
    data = gql(config.CINEPOLIS_LOCATIONS_URL, CINEMAS_QUERY,
               {"country": config.CINEPOLIS_COUNTRY, "city": city_id}, stats)
    out = [e["node"] for e in data["cinemas"]["edges"]]
    for c in out:
        c.setdefault("cityId", city_id)
    return out


def movies_for(cinema_ids, category="now-playing", stats=None):
    """Películas en cartelera para un lote de cines. Pagina por cursor."""
    out, after = [], None
    while True:
        data = gql(config.CINEPOLIS_BILLBOARDS_URL, MOVIES_QUERY, {
            "countryId": config.CINEPOLIS_COUNTRY, "category": category,
            "cinemas": ",".join(cinema_ids), "limit": config.CINEPOLIS_PAGE_SIZE, "after": after,
        }, stats)
        block = data["movies"]
        edges = block.get("edges") or []
        out.extend(e["node"] for e in edges)
        info = block.get("pageInfo") or {}
        if not edges or not info.get("hasNextPage") or not info.get("endCursor"):
            return out
        after = info["endCursor"]


def coming_soon(stats=None):
    """Títulos de "Próximamente" (cinepolis.com/mx/proximamente) de todo el país, con `releaseDate`: los que ya tienen
    funciones a la venta son la preventa (verificado 2026-09-25: 42 títulos en una página, sin filtro de cines)."""
    out, after = [], None
    while True:
        data = gql(config.CINEPOLIS_BILLBOARDS_URL, MOVIES_QUERY, {
            "countryId": config.CINEPOLIS_COUNTRY, "category": "coming-soon", "limit": config.CINEPOLIS_PAGE_SIZE, "after": after,
        }, stats)
        block = data["movies"]
        edges = block.get("edges") or []
        out.extend(e["node"] for e in edges)
        info = block.get("pageInfo") or {}
        if not edges or not info.get("hasNextPage") or not info.get("endCursor"):
            return out
        after = info["endCursor"]


def billboard(movie_id, cinema_ids, tz, stats=None):
    data = gql(config.CINEPOLIS_BILLBOARDS_URL, BILLBOARD_QUERY, {
        "countryId": config.CINEPOLIS_COUNTRY, "movieId": movie_id,
        "cinemas": ",".join(cinema_ids), "timezone": tz,
    }, stats)
    return data.get("billboard") or {}


def _batch(unit, tz, stats):
    """Películas y horarios de un lote de cines. Levanta si falla cualquier llamada: un lote a medias daría por
    canceladas las funciones de las películas que faltan."""
    movies, billboards = {}, []
    batch = unit["cinema_ids"]
    found = movies_for(batch, stats=stats)
    for m in found:
        movies.setdefault(m["id"], m)
        bb = billboard(m["id"], batch, tz, stats)
        billboards.append({"movie_id": m["id"], "cinemas": batch,
                           "dates": bb.get("dates") or [], "schedules": bb.get("schedules") or []})
    return {"movies": movies, "billboards": billboards}


def snapshot(city_ids=None):
    """Crudo completo: cines de cada ciudad, catálogo de películas y horarios por lotes de hasta 30 cines.

    Dos pasadas de unidades (`scraper/units.py`): el catálogo de cines, una por ciudad (una ciudad que falla queda
    registrada y sus cines no se piden), y la cartelera, un lote por estado de INEGI (`units.pack_by_state`; los estados
    chicos comparten lote). Solo las unidades fallidas del catálogo se guardan en `units`; las de cartelera, todas.

    Los lotes no se agrupan por zona horaria: `billboard` devuelve cada función en la hora local de su cine sin
    importar el parámetro `timezone` (verificado 2026-09-11 con un lote Tijuana + CDMX); se manda el de la mayoría."""
    stats = {"calls": 0}
    city_ids = list(city_ids or config.CINEPOLIS_CITIES) or sorted(c["id"] for c in list_cities(stats))
    catalog = units.run_units(
        [{"unit": f"ciudad-{city}", "label": f"Catálogo de cines de {city}", "city_ids": [city],
          "state_codes": [states.state_code("cinepolis", None, city)]} for city in city_ids],
        lambda u, st: list_cinemas(u["city_ids"][0], st))
    cinemas = sorted((c for _, found in catalog if found for c in found), key=lambda c: c["id"])
    for c in cinemas:
        c["state_code"] = states.state_code("cinepolis", c["id"], c.get("cityId"))
    tz_counts = Counter(c.get("timezone") for c in cinemas if c.get("timezone"))
    tz = tz_counts.most_common(1)[0][0] if tz_counts else config.PILOT_TIMEZONE

    batches = units.pack_by_state(cinemas)
    for b in batches:
        b["label"] = " + ".join(f"{states.STATES.get(code, 'Sin estado')}{' (' + b['parts'][code] + ')' if b['parts'][code] else ''}"
                                for code in b["state_codes"])
    results = units.run_units(batches, lambda u, st: _batch(u, tz, st))

    raw = {
        "chain": "cinepolis", "city_ids": city_ids, "timezone": tz,
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cinemas": cinemas, "movies": {}, "billboards": [],
        "units": [r for r, _ in catalog if not r["ok"]],
    }
    for record, data in results:
        if data is not None:
            for mid, m in data["movies"].items():
                raw["movies"].setdefault(mid, m)
            raw["billboards"].extend(data["billboards"])
        raw["units"].append(record)
    raw["calls"] = stats["calls"] + sum(r["calls"] for r, _ in catalog) + sum(r["calls"] for r, _ in results)
    return raw
