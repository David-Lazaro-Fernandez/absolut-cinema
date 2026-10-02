"""Cartelera y precios de Cinemas WTC (CDMX, 12 salas, 5 VIP).

Fuente: la API OCAPI de Vista (`digital-api.cinemaswtc.com/ocapi/v1`). Verificado 2026-10-02.
- La API pide un token anónimo. El token está en el `__NEXT_DATA__` de la página del cine (`gasToken`) y dura 12 h.
- `film-screening-dates` da los días con funciones.
- `showtimes/by-business-date/{día}` da las funciones del día. `relatedData` trae títulos, salas y clasificaciones.
- `showtimes/{id}/ticket-prices` da los boletos de una función.

Una sede, una unidad de captura.
"""
import json
import re
from datetime import datetime, timezone

from . import config, units
from .http import ApiError, AuthError, request_json, request_text

# La API da 0, 0. Coordenadas de OpenStreetMap, verificado 2026-10-02. La llave es el siteId de Vista.
SEDES = {"01": {"name": "Cinemas WTC", "lat": 19.3941, "lng": -99.1739}}
_TOKEN = re.compile(r'"gasToken":"([^"]+)"')


def token(stats=None):
    """El token anónimo de la API."""
    html = request_text(config.WTC_SITE_URL)
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    found = _TOKEN.search(html)
    if not found:
        raise AuthError("Cinemas WTC: la página ya no trae el token de la API (gasToken)")
    return found.group(1)


def _get(path, tok, stats):
    stats["calls"] = stats.get("calls", 0) + 1
    return request_json(f"{config.WTC_API_URL}/{path}", headers={"Authorization": f"Bearer {tok}"})


_LANGUAGE = {"SUB": "subtitled", "ESP": "spanish", "DOB": "spanish"}


def split_title(title):
    """'Digger SUB' → ('Digger', 'subtitled'). Sin sufijo de idioma, `other`."""
    head, _, tail = (title or "").strip().rpartition(" ")
    return (head, _LANGUAGE[tail.upper()]) if head and tail.upper() in _LANGUAGE else (title, "other")


def is_vip(screen_name):
    return "VIP" in (screen_name or "").upper()


def _fetch(unit, stats):
    tok = token(stats)
    site, = unit["cinema_ids"]
    screening = _get(f"film-screening-dates?siteIds={site}", tok, stats)
    dates = sorted({d["businessDate"] for d in screening.get("filmScreeningDates") or []})[:unit["days"]]
    days, prices = [], {}
    for date in dates:
        day = _get(f"showtimes/by-business-date/{date}?siteIds={site}", tok, stats)
        if "showtimes" not in day:
            raise ApiError(f"Cinemas WTC {date}: la respuesta no trae funciones")
        days.append(day)
        screens = {s["id"]: s["name"]["text"] for s in day.get("relatedData", {}).get("screens") or []}
        # ponytail: lee el precio de una función por día y tipo de sala. Si WTC cobra distinto por horario, leer cada función.
        for show in day["showtimes"]:
            key = f"{date}:{'vip' if is_vip(screens.get(show['screenId'])) else 'plex'}"
            if key not in prices:
                prices[key] = _get(f"showtimes/{show['id']}/ticket-prices", tok, stats)
    return {"days": days, "prices": prices}


def fare(response):
    """Respuesta de `ticket-prices` → `fare_json`. El boleto por defecto (Adulto) es el general. Sin boletos, None."""
    names = {t["id"]: (t.get("description") or {}).get("text") for t in (response or {}).get("relatedData", {}).get("ticketTypes") or []}
    tickets = [{"name": names.get(p.get("ticketTypeId")), "cents": round(p["price"]["valueIncludingTax"] * 100),
                "default": bool(p.get("isDefault"))} for p in (response or {}).get("ticketPrices") or []]
    general = next((t["cents"] for t in tickets if t["default"]), None)
    if not general:
        return None
    return json.dumps({"general_cents": general, "tickets": [{"name": t["name"], "cents": t["cents"]} for t in tickets]})


def snapshot(days=None):
    """Crudo de WTC: la respuesta de cada día y los boletos por día y tipo de sala. `days` limita los días (pruebas)."""
    unit = {"unit": "wtc", "label": "Cinemas WTC", "cinema_ids": sorted(SEDES), "days": days}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "wtc",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "days": data["days"] if data else [],
        "prices": data["prices"] if data else {},
        "units": [record],
        "calls": record["calls"],
    }
