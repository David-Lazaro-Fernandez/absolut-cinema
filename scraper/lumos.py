"""Cartelera y precios de los cines que venden con la web Lumos de Vista: Cinemas WTC (CDMX) y Cinery (Guadalajara).

Fuente: la API OCAPI de Vista de cada cine (`config.LUMOS`). Verificado 2026-10-02.
- La API pide un token anónimo. El token está en el `__NEXT_DATA__` de la web del cine (`gasToken`) y dura 12 h.
- `film-screening-dates` da los días con funciones.
- `showtimes/by-business-date/{día}` da las funciones del día. `relatedData` trae títulos, salas, atributos y
  clasificaciones.
- `showtimes/{id}/ticket-prices` da los boletos de una función.

Cada cine es una cadena con una sede y una unidad de captura.
"""
import json
import re
from datetime import datetime, timezone

from . import config, units
from .http import ApiError, AuthError, request_json, request_text

# La API da 0, 0. Coordenadas de OpenStreetMap, verificado 2026-10-02. La llave es el siteId de Vista.
SEDES = {"wtc": {"01": {"name": "Cinemas WTC", "lat": 19.3941, "lng": -99.1739}},
         "cinery": {"1": {"name": "Cinery", "lat": 20.7021, "lng": -103.3764}}}
_TOKEN = re.compile(r'"gasToken":"([^"]+)"')
# WTC marca el idioma con un sufijo del título; Cinery, con un atributo de la función.
_SUFFIX_LANGUAGE = {"SUB": "subtitled", "ESP": "spanish", "DOB": "spanish"}
_ATTRIBUTE_LANGUAGE = {"subtitulada": "subtitled", "doblada al español": "spanish"}


def token(chain, stats):
    """El token anónimo de la API de `chain`."""
    html = request_text(config.LUMOS[chain]["site_url"])
    stats["calls"] += 1
    found = _TOKEN.search(html)
    if not found:
        raise AuthError(f"{chain}: la web ya no trae el token de la API (gasToken)")
    return found.group(1)


def split_title(title):
    """'Digger SUB' → ('Digger', 'subtitled'). Sin sufijo de idioma, (título, None)."""
    head, _, tail = (title or "").strip().rpartition(" ")
    return (head, _SUFFIX_LANGUAGE[tail.upper()]) if head and tail.upper() in _SUFFIX_LANGUAGE else (title, None)


def attribute_language(names):
    """El idioma de los atributos de una función ('Subtitulada', 'Doblada al español'), o None."""
    return next((_ATTRIBUTE_LANGUAGE[n.lower()] for n in names if n.lower() in _ATTRIBUTE_LANGUAGE), None)


def is_vip(screen_name):
    return "VIP" in (screen_name or "").upper()


def price_key(date, show, screen_name):
    """La llave del precio de una función: día, tipo de sala y 2D o 3D."""
    return f"{date}:{'vip' if is_vip(screen_name) else 'plex'}:{'3d' if show.get('requires3dGlasses') else '2d'}"


def _fetch(unit, stats):
    chain, (site,) = unit["unit"], unit["cinema_ids"]
    api, tok = config.LUMOS[chain]["api_url"], token(chain, stats)

    def get(path):
        stats["calls"] += 1
        return request_json(f"{api}/{path}", headers={"Authorization": f"Bearer {tok}"})

    screening = get(f"film-screening-dates?siteIds={site}")
    dates = sorted({d["businessDate"] for d in screening.get("filmScreeningDates") or []})[:unit["days"]]
    days, prices = [], {}
    for date in dates:
        day = get(f"showtimes/by-business-date/{date}?siteIds={site}")
        if "showtimes" not in day:
            raise ApiError(f"{chain} {date}: la respuesta no trae funciones")
        days.append(day)
        screens = {s["id"]: s["name"]["text"] for s in day.get("relatedData", {}).get("screens") or []}
        # ponytail: lee el precio de una función por llave (`price_key`). Si el cine cobra distinto por horario, leer
        # cada función.
        for show in day["showtimes"]:
            key = price_key(date, show, screens.get(show["screenId"]))
            if key not in prices:
                prices[key] = get(f"showtimes/{show['id']}/ticket-prices")
    return {"days": days, "prices": prices}


def fare(response):
    """Respuesta de `ticket-prices` → `fare_json`. El boleto por defecto es el general. Sin boletos, None."""
    names = {t["id"]: (t.get("description") or {}).get("text") for t in (response or {}).get("relatedData", {}).get("ticketTypes") or []}
    tickets = [{"name": names.get(p.get("ticketTypeId")), "cents": round(p["price"]["valueIncludingTax"] * 100),
                "default": bool(p.get("isDefault"))} for p in (response or {}).get("ticketPrices") or []]
    general = next((t["cents"] for t in tickets if t["default"]), None)
    if not general:
        return None
    return json.dumps({"general_cents": general, "tickets": [{"name": t["name"], "cents": t["cents"]} for t in tickets]})


def snapshot(chain, days=None):
    """Crudo de `chain`: la respuesta de cada día y los boletos por llave de precio. `days` limita los días (pruebas)."""
    sedes = SEDES[chain]
    unit = {"unit": chain, "label": next(iter(sedes.values()))["name"], "cinema_ids": sorted(sedes), "days": days}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": chain,
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": sedes,
        "days": data["days"] if data else [],
        "prices": data["prices"] if data else {},
        "units": [record],
        "calls": record["calls"],
    }
