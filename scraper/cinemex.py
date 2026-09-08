"""Cliente de la API REST de Cinemex y snapshot de un conjunto de áreas."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import config
from .http import request_json

HEADERS = {"X-API-Consumer-Key": config.CINEMEX_CONSUMER_KEY}


def get(path, params=None, stats=None):
    url = config.CINEMEX_BASE_URL + path
    if params:
        url += "?" + urlencode(params)
    data = request_json(url, headers=HEADERS)
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    return data


def list_cinemas(stats=None):
    return get("cinemas/", stats=stats)


def area_billboard(area_id, date=None, stats=None):
    """Cartelera de todos los cines del área para un día. Sin `date` devuelve el día inicial."""
    params = {"include_dates": 1}
    if date:
        params["date"] = date
    else:
        params["initial"] = 1
    return get(f"cinemas/area/{area_id}/movies/", params, stats)


# Campos pesados que no aportan a la cartelera (sinopsis, pósters, colores, mapas de asientos).
_MOVIE_DROP = {"cover", "poster", "poster_small", "poster_medium", "poster_big", "poster_gif", "poster_mp4",
               "poster_featured", "poster_featured_web", "featured_bg", "images", "colors", "extra", "url",
               "featured", "featured_text", "display_title", "spotlight", "score"}
_INFO_DROP = {"sinopsis", "trailer", "imdb_url", "cast"}
_SESSION_DROP = {"seat_types_override", "url", "payment_methods"}
_CINEMA_DROP = {"info", "image", "maintenance_message", "alt_cinemas", "candybar", "includeQr", "market"}


def _slim(payload):
    """Quita del payload de área los campos que no describen funciones. Reduce ~10x el crudo."""
    for c in payload.get("cinemas") or []:
        for k in _CINEMA_DROP:
            c.pop(k, None)
        for m in c.get("movies") or []:
            for k in _MOVIE_DROP:
                m.pop(k, None)
            info = m.get("info")
            if isinstance(info, dict):
                for k in _INFO_DROP:
                    info.pop(k, None)
            for v in m.get("versions") or []:
                for s in v.get("sessions") or []:
                    for k in _SESSION_DROP:
                        s.pop(k, None)
    return payload


def _payload_date(payload):
    """Fecha a la que corresponde un payload, inferida de sus funciones."""
    counts = Counter()
    for c in payload.get("cinemas") or []:
        for m in c.get("movies") or []:
            for v in m.get("versions") or []:
                for s in v.get("sessions") or []:
                    dt = s.get("datetime") or ""
                    if len(dt) >= 10:
                        counts[dt[:10]] += 1
    return counts.most_common(1)[0][0] if counts else None


def snapshot(area_ids=None, days_ahead=config.CINEMEX_DAYS_AHEAD):
    area_ids = area_ids or config.CINEMEX_AREA_IDS
    stats = {"calls": 0}
    today = datetime.now(ZoneInfo(config.PILOT_TIMEZONE)).date()
    horizon = today + timedelta(days=days_ahead)
    raw = {
        "chain": "cinemex", "area_ids": area_ids,
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "areas": [],
    }
    for area_id in area_ids:
        first = area_billboard(area_id, stats=stats)
        available = first.get("dates") or []
        wanted = [d for d in available if today.isoformat() <= d <= horizon.isoformat()]
        # Por la tarde-noche cada área deja de listar el día en curso en `dates`, pero `date=hoy`
        # sigue devolviendo las funciones que faltan. Sin esto, el diff las daba por canceladas
        # (502 falsas "removed" el 2026-09-07 a las 19:00). Pedimos hoy siempre.
        if today.isoformat() not in wanted:
            wanted.insert(0, today.isoformat())
        days = {}
        first_date = _payload_date(first)
        if first_date and first_date in wanted:
            days[first_date] = first
        for d in wanted:
            if d not in days:
                days[d] = area_billboard(area_id, d, stats)
        raw["areas"].append({
            "area_id": area_id, "dates_available": available,
            "days": [{"date": d, "data": _slim(days[d])} for d in sorted(days)],
        })
    raw["calls"] = stats["calls"]
    return raw
