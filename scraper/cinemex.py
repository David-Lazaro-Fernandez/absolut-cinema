"""Cliente de la API REST de Cinemex y snapshot de un conjunto de estados (por defecto, todos)."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import config, units
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


def list_states(stats=None):
    """Estados con sus áreas: [{id, name, areas: [{id, name, state_id}]}] (31 el 2026-09-11)."""
    return get("states/", stats=stats)


def state_billboard(state_id, date=None, stats=None):
    """Cartelera de todos los cines del estado para un día. Sin `date` devuelve el día inicial."""
    params = {"include_dates": 1}
    if date:
        params["date"] = date
    else:
        params["initial"] = 1
    return get(f"cinemas/state/{state_id}/movies/", params, stats)


# Campos pesados que no aportan a la cartelera (sinopsis, pósters, colores, mapas de asientos).
_MOVIE_DROP = {"cover", "poster", "poster_small", "poster_medium", "poster_big", "poster_gif", "poster_mp4",
               "poster_featured", "poster_featured_web", "featured_bg", "images", "colors", "extra", "url",
               "featured", "featured_text", "display_title", "spotlight", "score"}
_INFO_DROP = {"sinopsis", "trailer", "imdb_url", "cast"}
_SESSION_DROP = {"seat_types_override", "url", "payment_methods"}
_CINEMA_DROP = {"info", "image", "maintenance_message", "alt_cinemas", "candybar", "includeQr", "market"}


def _slim(payload):
    """Quita del payload los campos que no describen funciones. Reduce ~10x el crudo."""
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


def _state_days(state_id, today, horizon, stats):
    """La cartelera de un estado, de hoy a `horizon`: {state_id, dates_available, days}. Levanta si falla cualquier día:
    un estado a medias daría por canceladas las funciones de los días que faltan."""
    first = state_billboard(state_id, stats=stats)
    available = first.get("dates") or []
    wanted = [d for d in available if today.isoformat() <= d <= horizon.isoformat()]
    # Por la tarde-noche cada estado deja de listar el día en curso en `dates`, pero `date=hoy`
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
            days[d] = state_billboard(state_id, d, stats)
    return {"state_id": state_id, "dates_available": available,
            "days": [{"date": d, "data": _slim(days[d])} for d in sorted(days)]}


def state_days_after(state_id, after, stats=None):
    """La cartelera de un estado para cada fecha que publica después de `after` (ISO): las preventas lejanas que la
    captura, que llega a `CINEMEX_DAYS_AHEAD`, no pide. Mismo formato que una unidad del snapshot."""
    first = state_billboard(state_id, stats=stats)
    dates = [d for d in first.get("dates") or [] if d > after]
    return {"state_id": str(state_id), "dates_available": first.get("dates") or [],
            "days": [{"date": d, "data": _slim(state_billboard(state_id, d, stats))} for d in dates]}


def snapshot(state_ids=None, days_ahead=config.CINEMEX_DAYS_AHEAD):
    """Crudo completo: por estado, la cartelera de cada día desde hoy hasta `days_ahead`. Cada estado es una unidad
    (`scraper/units.py`): uno que falla queda en `units` con su error y no tumba a los demás."""
    stats = {"calls": 0}
    catalog = list_states(stats)
    names = {int(s["id"]): s.get("name") for s in catalog}
    state_ids = list(state_ids or config.CINEMEX_STATES) or sorted(names)
    today = datetime.now(ZoneInfo(config.PILOT_TIMEZONE)).date()
    horizon = today + timedelta(days=days_ahead)
    todo = [{"unit": f"estado-{sid}", "label": f"{names.get(sid) or 'Estado'} (estado {sid} de Cinemex)",
             "state_ids": [str(sid)]} for sid in state_ids]
    results = units.run_units(todo, lambda u, st: _state_days(int(u["state_ids"][0]), today, horizon, st),
                              workers=config.CINEMEX_WORKERS)
    raw = {
        "chain": "cinemex", "state_ids": state_ids,
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "states": [], "units": [],
    }
    for record, data in results:
        if data is not None:
            raw["states"].append(data)
            record["cinema_ids"] = sorted({str(c["id"]) for day in data["days"] for c in day["data"].get("cinemas") or []})
        raw["units"].append(record)
    raw["calls"] = stats["calls"] + sum(r["calls"] for r, _ in results)
    return raw
