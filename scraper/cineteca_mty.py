"""Cliente de la Cineteca Nuevo León "Alejandra Rangel Hinojosa" (CONARTE, Monterrey, cine independiente) y snapshot
de su cartelera.

La cartelera es la página de WordPress `conarte.org.mx/cineteca/?fecha=AAAAMMDD`: en HTML, las funciones de ese día con
hora, título y enlace a la ficha de la película (su slug). No hay id de función, sala, idioma, clasificación ni duración;
la API de WordPress (`wp-json/wp/v2/cineteca`) tampoco trae las funciones. Verificado 2026-09-30.

Toda la cineteca es una unidad de captura, como la Cineteca Nacional: una sede, una página por día. Si un día falla, la
unidad entera falla y `run.py` conserva el tablero anterior. Solo stdlib.
"""
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from . import config, units
from .http import ApiError, request_text

# Coordenadas del punto "Cineteca" de OpenStreetMap en el Centro de las Artes, Parque Fundidora (verificado 2026-09-30).
# Nuevo León (state_code 19, en cinema_states.csv). cinema_id = city_id = la sede.
SEDES = {"centro-artes": {"name": "Cineteca Nuevo León", "lat": 25.6778, "lng": -100.2845}}


class _DayPage(HTMLParser):
    """Funciones de la página de un día: [{`slug`, `title`, `times`}], con `times` en 'HH:MM'."""

    def __init__(self):
        super().__init__()
        self.shows, self._show, self._in = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        href = a.get("href") or ""
        if tag == "a" and "max_wrap" in (a.get("class") or "") and "/cineteca/" in href:
            self._show = {"slug": urllib.parse.urlparse(href).path.rstrip("/").rsplit("/", 1)[-1], "title": "", "times": []}
        elif self._show is not None and tag == "p" and "schedule_hours" in (a.get("class") or ""):
            self._in = "times"
        elif self._show is not None and tag == "h2":
            self._in = "title"

    def handle_endtag(self, tag):
        if tag == "a" and self._show is not None:
            self.shows.append(self._show)
            self._show = None
        elif tag in ("p", "h2"):
            self._in = None

    def handle_data(self, data):
        if self._in == "times":
            self._show["times"] += [f"{int(h):02d}:{m}" for h, m in re.findall(r"(\d{1,2}):(\d{2})", data)]
        elif self._in == "title":
            self._show["title"] += data.strip()


def parse_day(html):
    """Funciones de la página de un día (ver `_DayPage`)."""
    page = _DayPage()
    page.feed(html)
    return page.shows


def day_page(date, stats=None):
    """HTML de la cartelera de un día (`YYYY-MM-DD`)."""
    fecha = date.replace("-", "")
    html = request_text(config.CINETECA_MTY_URL + "?" + urllib.parse.urlencode({"fecha": fecha}))
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    # La página repite la fecha pedida en un campo oculto. Sin él, cambió de forma o ignoró la fecha: leerla cerraría
    # funciones que siguen vigentes.
    if f'id="fecha" value="{fecha}"' not in html:
        raise ApiError(f"Cineteca NL {date}: la página no es la cartelera de ese día")
    return html


def _fetch(unit, stats):
    return {"days": [{"date": date, "html": day_page(date, stats)} for date in unit["dates"]]}


def snapshot(dates=None, days_ahead=None):
    """Crudo de la Cineteca NL: la sede y el HTML de la cartelera por día (`days`). `dates` fija los días (pruebas); si
    no, los próximos `days_ahead` (config.CINETECA_DAYS_AHEAD) desde hoy en la zona de referencia."""
    if dates is None:
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(config.PILOT_TIMEZONE)).date()
        dates = [(today + timedelta(days=i)).isoformat() for i in range(days_ahead or config.CINETECA_DAYS_AHEAD)]
    unit = {"unit": "cineteca_mty", "label": "Cineteca Nuevo León", "cinema_ids": sorted(SEDES), "dates": list(dates)}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "cineteca_mty",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dates": list(dates),
        "sedes": SEDES,
        "days": data["days"] if data else [],
        "units": [record],
        "calls": record["calls"],
    }
