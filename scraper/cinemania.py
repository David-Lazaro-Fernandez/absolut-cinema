"""Cartelera de Cinemanía (Plaza Loreto, San Ángel, CDMX).

Fuente: WordPress, una página por día de la semana de cine (`cartelera-nueva-2/?dia=jueves` … `miercoles`).
Verificado 2026-10-02.
- La pestaña de cada día trae su fecha ("01 OCT."). La pestaña pedida tiene la clase `activo`.
- Cada película trae título, clasificación, género, duración, horas y el enlace a Passline.
- No hay id de función, sala, idioma ni precio. Passline pone una sala de espera (queue-it) y no se lee.

Una sede, una unidad de captura.
"""
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser

from . import config, units
from .http import ApiError, request_text

# Coordenadas de OpenStreetMap, verificado 2026-10-02.
SEDES = {"loreto": {"name": "Cinemanía", "lat": 19.3396, "lng": -99.1925}}
DAYS = ("jueves", "viernes", "sabado", "domingo", "lunes", "martes", "miercoles")
_MONTHS = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")


class _DayPage(HTMLParser):
    """`active`, `dates` ({dia: '01 OCT.'}) y `films` ([{`title`, `meta`, `times`, `slug`}])."""

    def __init__(self):
        super().__init__()
        self.active, self.dates, self.films = None, {}, []
        self._tab, self._field = None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "a" and "cinemania-dia" in cls:
            self._tab = (a.get("href") or "").rpartition("dia=")[2]
            if "activo" in cls:
                self.active = self._tab
        elif tag == "span" and "cinemania-dia-fecha" in cls and self._tab:
            self._field = "tab_date"
        elif tag == "div" and "cinemania-horario-card" in cls:
            self.films.append({"title": "", "meta": "", "times": [], "slug": None})
        elif self.films and tag == "h3":
            self._field = "title"
        elif self.films and tag == "div" and "cinemania-meta" in cls:
            self._field = "meta"
        elif self.films and tag == "span" and "cinemania-hora" in cls:
            self._field = "time"
        elif self.films and tag == "a" and "sitio-evento/" in (a.get("href") or ""):
            self.films[-1]["slug"] = a["href"].rstrip("/").rpartition("/")[2]

    def handle_endtag(self, tag):
        if tag in ("span", "h3", "div"):
            self._field = None
        if tag == "a":
            self._tab = None

    def handle_data(self, data):
        text = data.strip()
        if not text or not self._field:
            return
        if self._field == "tab_date":
            self.dates[self._tab] = text
        elif self._field == "time":
            self.films[-1]["times"].append(text)
        else:
            self.films[-1][self._field] += text + " "


def parse_day(html):
    """La página de un día: `active`, `dates` y `films`."""
    page = _DayPage()
    page.feed(html)
    return page


def tab_date(text, today):
    """'01 OCT.' → 'YYYY-MM-DD'. La página no da el año. Usa el de `today`; si el mes quedó atrás más de seis
    meses, el siguiente. None si no se puede leer."""
    m = re.fullmatch(r"(\d{1,2}) (\w{3})\.?", (text or "").strip().upper())
    if not m or m.group(2) not in _MONTHS:
        return None
    month = _MONTHS.index(m.group(2)) + 1
    year = today.year + 1 if month < today.month - 6 else today.year
    return date(year, month, int(m.group(1))).isoformat()


def meta(text):
    """'B15 •Drama social •88 min' → ('B15', 'Drama social', 88)."""
    parts = [p.strip() for p in text.split("•")]
    minutes = re.fullmatch(r"(\d+) min", parts[-1]) if parts else None
    return (parts[0] or None if parts else None, parts[1] if len(parts) > 2 else None,
            int(minutes.group(1)) if minutes else None)


def day_page(dia, stats):
    html = request_text(f"{config.CINEMANIA_URL}?dia={dia}")
    stats["calls"] += 1
    # Otra pestaña activa cierra funciones vigentes. Si no es la pedida, la página cambió.
    if parse_day(html).active != dia:
        raise ApiError(f"Cinemanía {dia}: la página no es la cartelera de ese día")
    return html


def _fetch(unit, stats):
    return {"days": [{"dia": dia, "html": day_page(dia, stats)} for dia in unit["dias"]]}


def snapshot(dias=DAYS):
    """Crudo de Cinemanía: el HTML de cada día. `dias` limita los días (pruebas)."""
    unit = {"unit": "cinemania", "label": "Cinemanía", "cinema_ids": sorted(SEDES), "dias": list(dias)}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "cinemania",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sedes": SEDES,
        "days": data["days"] if data else [],
        "units": [record],
        "calls": record["calls"],
    }

