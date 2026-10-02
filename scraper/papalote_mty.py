"""Cartelera y precios de la Megapantalla IMAX de Papalote Museo del Niño Monterrey.

Fuentes, verificado 2026-10-02:
- La cartelera de WordPress (`papalotemty.org.mx/cartelera/`) enlaza las fichas. Cada ficha enlaza su plan de Fever.
- La API pública de Fever (`plans/{plan}/place/{lugar}/sessions/`) da cada función con hora, boleto y precio. Pagina
  por días (`next`).
- Los horarios de la ficha se escriben a mano ("01 al 04 OCT"). No se leen.
- Los documentales comparten un plan. Su título está en la etiqueta del boleto ("T-Rex | SP").

Una sede, una unidad de captura.
"""
import html
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, units
from .http import ApiError, request_json, request_text

# Coordenadas de OpenStreetMap, verificado 2026-10-02.
SEDES = {"fundidora": {"name": "Papalote Monterrey", "lat": 25.6768, "lng": -100.2845}}
_FILM_LINK = re.compile(r'href="(https://papalotemty\.org\.mx/cartelera/[^"/]+/)"')
_PLAN_LINK = re.compile(r"feverup\.com/m/(\d+)")
_TITLE = re.compile(r"<title>(.*?)\s*(?:&#8211;|–)", re.S)


def films(stats):
    """Las fichas de la cartelera: [{`title`, `plans`}]."""
    page = request_text(config.PAPALOTE_MTY_URL)
    stats["calls"] += 1
    links = sorted(set(_FILM_LINK.findall(page)) - {config.PAPALOTE_MTY_URL})
    if not links:
        raise ApiError("Papalote MTY: la cartelera no enlaza ninguna película")
    out = []
    for url in links:
        film = request_text(url)
        stats["calls"] += 1
        title = _TITLE.search(film)
        out.append({"title": html.unescape(title.group(1)).strip() if title else None,
                    "plans": sorted(set(_PLAN_LINK.findall(film)))})
    return out


def sessions(plan, until, stats):
    """Las páginas de funciones de un plan, de hoy a `until` (`YYYY-MM-DD`)."""
    url = f"{config.FEVER_API_URL}/plans/{plan}/place/{config.FEVER_PLACE_ID}/sessions/"
    pages, query = [], ""
    while True:
        page = request_json(url + query, headers={"Accept-Language": "es-MX"})
        stats["calls"] += 1
        pages.append(page)
        nxt = page.get("next")
        if not nxt or nxt["date"] > until:
            return pages
        query = "?" + urllib.parse.urlencode(nxt)


def _fetch(unit, stats):
    listed = films(stats)
    plans = sorted({p for f in listed for p in f["plans"]})
    return {"films": listed, "sessions": {p: sessions(p, unit["until"], stats) for p in plans}}


def tickets(pages):
    """Los boletos de las páginas de un plan: [{`id`, `label`, `starts_at`, `price`}]."""
    out = []

    def walk(level):
        for item in (level or {}).get("items") or []:
            value = item.get("value") or {}
            if "price" in value and "starts_at_iso" in value:
                out.append({"id": value["id"], "label": value.get("label") or "", "starts_at": value["starts_at_iso"],
                            "price": value["price"]})
            walk(item.get("level"))
    for page in pages:
        walk(page.get("level"))
    return out


def label_title(label):
    """'T-Rex | SP Familiar' → 'T-Rex'. 'Acceso General Subtitulada' → None."""
    head, sep, _ = label.partition(" | ")
    return head.strip() if sep else None


def label_language(label):
    """'Subtitulada' → `subtitled`; 'SP' → `spanish`; sin marca, `other`."""
    if "subtitulad" in label.lower():
        return "subtitled"
    return "spanish" if re.search(r"\bSP\b|doblad", label, re.I) else "other"


def snapshot(days_ahead=None):
    """Crudo de Papalote MTY: las fichas y las páginas de Fever por plan, hasta `days_ahead` días."""
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(config.PILOT_TIMEZONE)).date()
    until = (today + timedelta(days=days_ahead or config.CINETECA_DAYS_AHEAD)).isoformat()
    unit = {"unit": "papalote_mty", "label": "Papalote Monterrey", "cinema_ids": sorted(SEDES), "until": until}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "papalote_mty",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "films": data["films"] if data else [],
        "sessions": data["sessions"] if data else {},
        "units": [record],
        "calls": record["calls"],
    }
