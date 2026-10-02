"""Cartelera y precios de Epic Cinemas (Metropolitan Center, Valle Oriente, Monterrey).

Fuente: el Connect API de Vista del cine, con el `connectapitoken` público de su web. Verificado 2026-10-02.
- `OData.svc/Sessions` da todas las funciones: sala, hora, butacas libres y grupo de precio (`PriceGroupCode`).
- `OData.svc/ScheduledFilms` da título, clasificación y duración.
- `RESTData.svc/cinemas/{cine}/sessions/{función}/tickets` da los boletos de una función.
- No trae idioma. Algunos títulos van en inglés y en español ("Heart of the Beast / El corazón de la bestia").

Una sede, una unidad de captura.
"""
import json
from datetime import datetime, timezone

from . import config, units
from .http import ApiError, request_json

# Coordenadas del Connect API (`Cinemas`), verificado 2026-10-02. La llave es el id de cine de Vista.
SEDES = {"0000000001": {"name": "Epic Cinemas Metropolitan Center", "lat": 25.6505, "lng": -100.3331}}


def _fetch(unit, stats):
    def get(path):
        stats["calls"] += 1
        return request_json(f"{config.EPIC_VISTA_URL}/{path}", headers={"connectapitoken": config.EPIC_CONNECT_TOKEN})

    cinema, = unit["cinema_ids"]
    sessions = [s for s in get("OData.svc/Sessions?$format=json").get("value") or [] if s["CinemaId"] == cinema]
    if not sessions:
        raise ApiError("Epic: el Connect API no trae funciones")
    films = get("OData.svc/ScheduledFilms?$format=json").get("value") or []
    # ponytail: lee el precio de una función por día y grupo de precio. Si el cine cobra distinto dentro de un grupo,
    # leer cada función.
    prices = {}
    for s in sessions[:unit["limit"]]:
        key = price_key(s)
        if key not in prices:
            prices[key] = get(f"RESTData.svc/cinemas/{cinema}/sessions/{s['SessionId']}/tickets").get("Tickets") or []
    return {"sessions": sessions[:unit["limit"]], "films": films, "prices": prices}


def price_key(session):
    """La llave del precio de una función: día y grupo de precio."""
    return f"{session['SessionBusinessDate'][:10]}:{session['PriceGroupCode']}"


def fare(tickets):
    """Boletos de una función → `fare_json`. El boleto "GENERAL" es el general. Sin él, None."""
    found = [{"name": t["Description"], "cents": t["PriceInCents"]} for t in tickets or [] if t.get("PriceInCents")]
    general = next((t["cents"] for t in found if t["name"].strip().upper() == "GENERAL"), None)
    if not general:
        return None
    return json.dumps({"general_cents": general, "tickets": found})


def title(text):
    """'Heart of the Beast / El corazón de la bestia' → 'El corazón de la bestia'."""
    return (text or "").rpartition(" / ")[2].strip()


def snapshot(limit=None):
    """Crudo de Epic: funciones, películas y boletos por llave de precio. `limit` limita las funciones (pruebas)."""
    unit = {"unit": "epic", "label": "Epic Cinemas", "cinema_ids": sorted(SEDES), "limit": limit}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "epic",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        **(data or {"sessions": [], "films": [], "prices": {}}),
        "units": [record],
        "calls": record["calls"],
    }
