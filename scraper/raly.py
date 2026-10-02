"""Cartelera de Cinemas Raly (Madero, centro de Monterrey).

Fuente: la página de WordPress `cinemasraly.com/horarios/`. Verificado 2026-10-02.
- Publica un solo horario que vale de lunes a domingo. La captura lo repite de hoy al miércoles de la semana de cine.
- Cada película va en un `blockquote`: el idioma ("DOBLADA"), el título y las horas en 12 h. Las horas llevan la
  clase `h-hora pm` o `h-hora am`; sin clase, se toma p.m.
- No hay id de función, sala ni duración.

Una sede, una unidad de captura.
"""
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from . import config, units
from .http import ApiError, request_text

# Coordenadas del mapa de su página de contacto, verificado 2026-10-02.
SEDES = {"madero": {"name": "Cinemas Raly", "lat": 25.6837, "lng": -100.2854}}
_WEDNESDAY = 2
_TIME = re.compile(r"\d{1,2}:\d{2}")
_LABELS = ("DOBLADA", "SUBTITULADA")


class _Schedule(HTMLParser):
    """Los textos de cada `blockquote`, en orden: [[(texto, 'am' | 'pm' | None)]]. La media del día solo la trae un
    texto dentro de un `span` `h-hora`."""

    def __init__(self):
        super().__init__()
        self.blocks, self._block, self._half = [], None, None

    def handle_starttag(self, tag, attrs):
        cls = (dict(attrs).get("class") or "").split()
        if tag == "blockquote":
            self._block = []
        elif self._block is not None and tag == "span" and "h-hora" in cls:
            self._half = next((c for c in cls if c in ("am", "pm")), None)

    def handle_endtag(self, tag):
        if tag == "span":
            self._half = None
        elif tag == "blockquote" and self._block is not None:
            self.blocks.append(self._block)
            self._block = None

    def handle_data(self, data):
        if self._block is not None and data.strip():
            self._block.append((data.strip(), self._half))


def parse(html):
    """Las películas de la página de horarios: [{`label`, `title`, `times`: [('3:40', 'pm')]}]. La página se edita a
    mano y el título va dentro o fuera del `span`: las horas se reconocen por su forma y el idioma por su palabra."""
    page = _Schedule()
    page.feed(html)
    films = []
    for block in page.blocks:
        times = [(text, half or "pm") for text, half in block if _TIME.fullmatch(text)]
        labels = [text for text, _ in block if text.upper() in _LABELS]
        titles = [text for text, _ in block if not _TIME.fullmatch(text) and text.upper() not in _LABELS]
        if titles and times:
            films.append({"label": " ".join(labels), "title": titles[0], "times": times})
    return films


def hour(text, half):
    """('3:40', 'pm') → '15:40'. ('12:15', 'pm') → '12:15'. None si no se puede leer."""
    try:
        return datetime.strptime(f"{text} {half}".upper(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return None


def dates(today):
    """De `today` al miércoles de su semana de cine (jueves a miércoles)."""
    return [(today + timedelta(days=i)).isoformat() for i in range((_WEDNESDAY - today.weekday()) % 7 + 1)]


def _fetch(unit, stats):
    html = request_text(config.RALY_URL)
    stats["calls"] += 1
    # Una página sin películas cierra todas las funciones. Si no hay ninguna, la página cambió.
    if not parse(html):
        raise ApiError("Raly: la página de horarios no trae películas")
    return html


def snapshot():
    """Crudo de Raly: el HTML de la página de horarios y los días a los que aplica."""
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(config.PILOT_TIMEZONE)).date()
    unit = {"unit": "raly", "label": "Cinemas Raly", "cinema_ids": sorted(SEDES)}
    (record, html), = units.run_units([unit], _fetch)
    return {
        "chain": "raly",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "dates": dates(today),
        "html": html or "",
        "units": [record],
        "calls": record["calls"],
    }
