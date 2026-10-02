"""Cartelera del Cine Cabañas (sala Guillermo del Toro del Museo Cabañas, centro de Guadalajara).

Fuente: la página de WordPress `museocabanas.jalisco.gob.mx/cine/`. Verificado 2026-10-02.
- Cada película o ciclo es una tarjeta con título, enlace y un texto escrito a mano con fechas, hora y precio:
  "8, 9 Y 10 de octubre, 19 h. Entrada $65" o "4 de septiembre, 16:30 h. y 2 de octubre, 17:30 h. Entrada gratuita".
- El año no viene en el texto.
- No hay id de función, sala, idioma ni duración. La venta es solo en taquilla.

Una sede, una unidad de captura.
"""
import html
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser

from . import config, units
from .http import ApiError, request_text

# Coordenadas de OpenStreetMap, verificado 2026-10-02.
SEDES = {"museo": {"name": "Cine Cabañas", "lat": 20.6769, "lng": -103.3377}}
_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre")
# Un grupo de fechas con su hora: "8, 9 Y 10 de octubre, 19 h" o "2 de octubre, 17:30 h".
_DATES = re.compile(r"((?:\d{1,2}\s*(?:,|\by\b)\s*)*\d{1,2}) de (\w+),?\s*(\d{1,2})(?::(\d{2}))?\s*h", re.I)
_PRICE = re.compile(r"\$\s?(\d+)")


class _Cards(HTMLParser):
    """Las tarjetas de la página: [{`slug`, `title`, `text`}]."""

    def __init__(self):
        super().__init__()
        self.cards, self._field = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "h5" and "eltdf-show-name" in cls:
            self.cards.append({"slug": None, "title": "", "text": ""})
            self._field = "title"
        elif self._field == "title" and tag == "a":
            self.cards[-1]["slug"] = (a.get("href") or "").rstrip("/").rpartition("/")[2]
        elif self.cards and tag == "div" and "eltdf-show-excerpt-holder" in cls:
            self._field = "text"

    def handle_endtag(self, tag):
        if tag in ("h5", "div"):
            self._field = None

    def handle_data(self, data):
        if self._field:
            self.cards[-1][self._field] += data


def parse(page):
    """Las tarjetas de la página, con el texto limpio (ver `_Cards`)."""
    cards = _Cards()
    cards.feed(page)
    return [{k: " ".join(html.unescape(v or "").split()) for k, v in c.items()} for c in cards.cards]


def shows(text, today):
    """'1 y 3 de octubre, 19 h.' → [('2026-10-01', '19:00'), ('2026-10-03', '19:00')]. El año es el de `today`, o el
    siguiente si el mes quedó atrás más de seis meses."""
    out = []
    for days, month, hh, mm in _DATES.findall(text):
        if month.lower() not in _MONTHS:
            continue
        number = _MONTHS.index(month.lower()) + 1
        year = today.year + 1 if number < today.month - 6 else today.year
        for day in re.findall(r"\d{1,2}", days):
            out.append((date(year, number, int(day)).isoformat(), f"{int(hh):02d}:{mm or '00'}"))
    return out


def price_cents(text):
    """El precio del texto en centavos: '$65' → 6500, 'gratuita' → 0. None si no lo dice."""
    found = _PRICE.search(text)
    if found:
        return int(found.group(1)) * 100
    return 0 if "gratuit" in text.lower() else None


def _fetch(unit, stats):
    page = request_text(config.CABANAS_URL)
    stats["calls"] += 1
    # Una página sin tarjetas cierra todas las funciones. Si no hay ninguna, la página cambió.
    if not parse(page):
        raise ApiError("Cine Cabañas: la página no trae películas")
    return page


def snapshot():
    """Crudo del Cine Cabañas: el HTML de su página de cine."""
    unit = {"unit": "cabanas", "label": "Cine Cabañas", "cinema_ids": sorted(SEDES)}
    (record, page), = units.run_units([unit], _fetch)
    return {
        "chain": "cabanas",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "html": page or "",
        "units": [record],
        "calls": record["calls"],
    }
