"""Cliente de la API GraphQL de Cinépolis y snapshot de una ciudad."""
import json
from collections import Counter
from datetime import datetime, timezone

from . import config
from .http import ApiError, request_json

HEADERS = {
    "x-apikey": config.CINEPOLIS_API_KEY,
    "country-id": config.CINEPOLIS_COUNTRY,
    "language": "ES",
}

CINEMAS_QUERY = """
query Cinemas($country: String!, $city: String!) {
  cinemas(country_id: $country, city_id: $city) {
    edges { node { id name vistaId timezone businessType lat lng } }
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


def list_cinemas(city_id=config.CINEPOLIS_CITY_ID, stats=None):
    data = gql(config.CINEPOLIS_LOCATIONS_URL, CINEMAS_QUERY,
               {"country": config.CINEPOLIS_COUNTRY, "city": city_id}, stats)
    return [e["node"] for e in data["cinemas"]["edges"]]


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


def billboard(movie_id, cinema_ids, tz, stats=None):
    data = gql(config.CINEPOLIS_BILLBOARDS_URL, BILLBOARD_QUERY, {
        "countryId": config.CINEPOLIS_COUNTRY, "movieId": movie_id,
        "cinemas": ",".join(cinema_ids), "timezone": tz,
    }, stats)
    return data.get("billboard") or {}


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def snapshot(city_id=config.CINEPOLIS_CITY_ID):
    """Crudo completo de la ciudad: cines, catálogo de películas y horarios por lote."""
    stats = {"calls": 0}
    cinemas = list_cinemas(city_id, stats)
    slugs = sorted(c["id"] for c in cinemas)
    tz_counts = Counter(c.get("timezone") for c in cinemas if c.get("timezone"))
    tz = tz_counts.most_common(1)[0][0] if tz_counts else config.PILOT_TIMEZONE

    raw = {
        "chain": "cinepolis", "city_id": city_id, "timezone": tz,
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cinemas": cinemas, "movies": {}, "billboards": [],
    }
    for batch in chunks(slugs, config.CINEPOLIS_BATCH_SIZE):
        movies = movies_for(batch, stats=stats)
        for m in movies:
            raw["movies"].setdefault(m["id"], m)
        for m in movies:
            bb = billboard(m["id"], batch, tz, stats)
            raw["billboards"].append({
                "movie_id": m["id"], "cinemas": batch,
                "dates": bb.get("dates") or [], "schedules": bb.get("schedules") or [],
            })
    raw["calls"] = stats["calls"]
    return raw
