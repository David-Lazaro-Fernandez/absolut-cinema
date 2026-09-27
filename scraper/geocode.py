"""Dirección → coordenadas para el recomendador del dashboard, con Nominatim (OpenStreetMap) y solo librería estándar.

No escribe nada: devuelve el mejor resultado de la búsqueda, acotado al país de `config.GEOCODER_COUNTRY`. Nominatim pide
una consulta por segundo como máximo y un User-Agent propio (`config.GEOCODER_USER_AGENT`); quien lo llama debe guardar
el resultado en caché y consultar solo cuando el usuario envía una dirección.
"""
import urllib.parse

from . import config
from .http import ApiError, request_json

__all__ = ["ApiError", "geocode"]


def geocode(address):
    """{lat, lng, label} del primer resultado para `address`, o None si no hay. `label` es la dirección que entendió el
    servicio, para mostrarla al usuario y que confirme el punto. Levanta `http.ApiError` si el servicio falla."""
    query = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1, "countrycodes": config.GEOCODER_COUNTRY,
                                    "accept-language": "es"})
    found = request_json(f"{config.GEOCODER_URL}?{query}", headers={"User-Agent": config.GEOCODER_USER_AGENT}, retries=1)
    if not found:
        return None
    return {"lat": float(found[0]["lat"]), "lng": float(found[0]["lon"]), "label": found[0].get("display_name", address)}
