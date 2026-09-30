"""Cliente de las salas de la FICG en Guadalajara (Cineteca FICG y Cineforo de la UdeG, cines independientes) y
snapshot de su cartelera.

Las dos venden en Veezi, cada una con su `siteToken`. La página pública de horarios de Veezi
(`sessions/?siteToken=…`) trae en HTML toda la cartelera vigente de la sede: película (código de Veezi), título,
clasificación, fecha sin año, hora en 12 h y el id de cada función. No da sala, idioma ni duración: la sala y el precio
viven en la página de compra de cada función, fuera de alcance. El idioma va en el título ("- SUBTITULADA",
"- DOBLADA"). Verificado 2026-09-30.

Cada sede es una unidad de captura (`scraper/units.py`): una página por sede. Si una falla, `run.py` conserva su
tablero anterior. Solo stdlib.
"""
import re
import urllib.parse
from datetime import date, datetime, timezone
from html.parser import HTMLParser

from . import config, units
from .http import ApiError, request_text

# Coordenadas de OpenStreetMap (Nominatim, verificado 2026-09-30). Las dos están en Jalisco (state_code 14, en
# cinema_states.csv). cinema_id = city_id = la sede.
SEDES = {
    "ficg": {"name": "Cineteca FICG", "lat": 20.7366, "lng": -103.3811},
    "cineforo": {"name": "Cineforo UdeG", "lat": 20.6751, "lng": -103.3590},
}
_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"), 1)}
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class _SessionsPage(HTMLParser):
    """Funciones de la página de horarios de Veezi: [{`film_code`, `title`, `rating`, `date_text`, `time_text`,
    `session_id`}]. La página repite cada función en dos pestañas (por fecha y por película)."""

    def __init__(self):
        super().__init__()
        self.shows, self._film, self._date, self._href, self._field = [], {}, None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "div" and "film" in cls:
            self._film = {}
        elif tag == "img" and "poster" in cls:
            # Una película sin póster no trae código: su `film_code` queda vacío.
            self._film["film_code"] = urllib.parse.parse_qs(urllib.parse.urlparse(a.get("src") or "").query).get("code", [None])[0]
        elif tag == "h3" and "title" in cls:
            self._field = "title"
        elif tag == "span" and "censor" in cls:
            self._field = "rating"
        elif tag == "h4" and "date" in cls:
            self._field = "date"
        elif tag == "a" and "/purchase/" in (a.get("href") or ""):
            self._href = a["href"]
        elif tag == "time" and self._href:
            self._field = "time"

    def handle_endtag(self, tag):
        self._field = None                  # una clasificación vacía no toma el texto que le sigue

    def handle_data(self, data):
        text = data.strip()
        if not text or not self._field:
            return
        if self._field == "date":
            self._date = text
        elif self._field == "time":
            session_id = urllib.parse.urlparse(self._href).path.rstrip("/").rsplit("/", 1)[-1]
            self.shows.append({**self._film, "date_text": self._date, "time_text": text, "session_id": session_id})
            self._href = None
        else:
            self._film[self._field] = text
        self._field = None


def parse_sessions(html):
    """Funciones de una página de horarios de Veezi, sin repetir (ver `_SessionsPage`)."""
    page = _SessionsPage()
    page.feed(html)
    return list({s["session_id"]: s for s in page.shows}.values())


def show_date(date_text, today):
    """'Wednesday 30, September' → 'YYYY-MM-DD'. Veezi no da el año: es el año, desde el de `today`, en que ese día cae
    en ese día de la semana. None si no se puede leer."""
    m = re.fullmatch(r"(\w+) (\d{1,2}), (\w+)", (date_text or "").strip())
    if not m or m.group(1).lower() not in _WEEKDAYS or m.group(3).lower() not in _MONTHS:
        return None
    weekday, day, month = _WEEKDAYS.index(m.group(1).lower()), int(m.group(2)), _MONTHS[m.group(3).lower()]
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d.weekday() == weekday:
            return d.isoformat()
    return None


def show_time(time_text):
    """'3:00 PM' → '15:00'; None si no se puede leer."""
    try:
        return datetime.strptime((time_text or "").strip().upper(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return None


def sessions_page(site_token, stats=None):
    """HTML de la página de horarios de Veezi de una sede."""
    # Veezi traduce fechas y horas según Accept-Language; en inglés el formato es el que lee `show_date`.
    html = request_text(config.VEEZI_SESSIONS_URL + "?" + urllib.parse.urlencode({"siteToken": site_token}),
                        headers={"Accept-Language": "en-US"})
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    # Sin esta lista la página cambió de forma o es una de error: leerla vacía cerraría todas las funciones.
    if "session-times" not in html:
        raise ApiError(f"Veezi {site_token}: la página de horarios no trae funciones")
    return html


def _fetch(unit, stats):
    code, = unit["cinema_ids"]
    return sessions_page(config.VEEZI_SITE_TOKENS[code], stats)


def snapshot():
    """Crudo de las dos sedes: el HTML de la página de horarios de cada una (`pages`, {sede: html}) y sus unidades."""
    plan = [{"unit": code, "label": s["name"], "cinema_ids": [code]} for code, s in SEDES.items()]
    done = units.run_units(plan, _fetch)
    return {
        "chain": "cineteca_gdl",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "pages": {record["unit"]: html for record, html in done if html is not None},
        "units": [record for record, _ in done],
        "calls": sum(record["calls"] for record, _ in done),
    }
