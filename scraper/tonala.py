"""Cartelera del Cine Tonalá (Roma Sur, CDMX).

Fuente: su taquilla en Red Access (`cinetonalaromasur.ordenaboletos.com.mx`). Verificado 2026-10-02.
- El sitio es de Next.js. Los datos están en los fragmentos `self.__next_f.push([1, "…"])` del HTML.
- La portada lista los eventos. La ruta empieza con la categoría: `cine/…` es cine; `artes-escenicas/…` no.
- La página de un evento trae `entertainments`: id y hora local de cada función.
- No trae sala, idioma, duración ni precio.

Una sede, una unidad de captura.
"""
import json
import re
from datetime import datetime, timezone

from . import config, units
from .http import ApiError, request_text

# Coordenadas de OpenStreetMap, verificado 2026-10-02.
SEDES = {"roma-sur": {"name": "Cine Tonalá", "lat": 19.4089, "lng": -99.1604}}
_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_EVENT_URL = re.compile(r'"url":"(cine/[^"]+)"')


def payload(html):
    """Los fragmentos de datos de Next.js de una página, unidos."""
    return "".join(json.loads(f'"{chunk}"') for chunk in _CHUNK.findall(html))


def _object_after(text, key):
    """El valor JSON que sigue a `"key":` en `text`, o None si no está."""
    at = text.find(f'"{key}":')
    if at < 0:
        return None
    value, _ = json.JSONDecoder().raw_decode(text, at + len(key) + 3)
    return value


def event_urls(home):
    """Las rutas de los eventos de cine de la portada (`cine/digger-2161`)."""
    return sorted(set(_EVENT_URL.findall(payload(home))))


def event(page):
    """El evento de una página: {`name`, `entertainments`: [{`id`, `celebrationDate`}]}."""
    text = payload(page)
    detail, shows = _object_after(text, "eventDetail"), _object_after(text, "entertainments")
    if detail is None or shows is None:
        raise ApiError("Tonalá: la página del evento no trae sus funciones")
    return {"name": detail.get("name"), "entertainments": shows}


def _fetch(unit, stats):
    home = request_text(config.TONALA_URL + "/")
    stats["calls"] += 1
    urls = event_urls(home)
    # Una portada vacía cierra todas las funciones. Si no hay eventos, la página cambió.
    if not urls:
        raise ApiError("Tonalá: la portada no lista eventos de cine")
    events = {}
    for url in urls[:unit["limit"]]:
        events[url] = event(request_text(f"{config.TONALA_URL}/{url}"))
        stats["calls"] += 1
    return events


def snapshot(limit=None):
    """Crudo de Tonalá: {ruta: evento}. `limit` limita los eventos (pruebas)."""
    unit = {"unit": "tonala", "label": "Cine Tonalá", "cinema_ids": sorted(SEDES), "limit": limit}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "tonala",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "events": data or {},
        "units": [record],
        "calls": record["calls"],
    }
