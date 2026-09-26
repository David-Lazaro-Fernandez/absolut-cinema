"""Cliente de la Cineteca Nacional (cine independiente de CDMX) y snapshot de su cartelera.

La cartelera es un JSON público (`obtener_cartelera.php?fecha=…`), una respuesta por día, con las tres sedes de CDMX.
No hay clave ni WAF. Cada función trae su sede y su `session_id` de Vista; el idioma va incrustado en el título (sufijos
DOB/DUB/SUB) y este endpoint no da género, duración ni distribuidora (viven en `detallePelicula.php`, fuera de alcance).

Toda la Cineteca se captura como una sola unidad (`scraper/units.py`): la fuente es un endpoint y las tres sedes se
piden juntas por fecha. Si un día falla tras los reintentos de `http.py`, la unidad entera falla y `run.py` no escribe
nada, así el tablero anterior queda intacto: no se puede releer por fecha y cerrar funciones futuras no leídas sería una
cancelación falsa. La ocupación (plano de asientos de Vista con token) vive en `scraper/sample.py`. Solo stdlib.
"""
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, units
from .http import ApiError, request_json

# Coordenadas de cada sede, tomadas del propio sitio de Vista (Browsing/Cinemas/Details, verificado 2026-09-26). Las
# tres están en la Ciudad de México (state_code 09, en cinema_states.csv). cinema_id = codigo_sede = cinemacode de Vista.
SEDES = {
    "001": {"name": "Cineteca Chapultepec", "lat": 19.3886, "lng": -99.2284},
    "002": {"name": "Cineteca de las Artes", "lat": 19.3563, "lng": -99.1356},
    "003": {"name": "Cineteca México", "lat": 19.3611, "lng": -99.1646},
}


def cartelera(date, stats=None):
    """Cartelera de un día (`YYYY-MM-DD`): la lista `data` del JSON, una entrada por película con sus sedes y horarios."""
    url = config.CINETECA_CARTELERA_URL + "?" + urllib.parse.urlencode({"busqueda": "", "fecha": date, "sede": ""})
    data = request_json(url)
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    if data.get("status") != "success":
        raise ApiError(f"cartelera {date}: status {data.get('status')!r}")
    return data.get("data") or []


def _fetch(unit, stats):
    """Cartelera de todos los días del alcance. Levanta si un día falla: una unidad a medias cerraría por error
    funciones futuras no leídas (no hay relectura por fecha; el tablero anterior se conserva si la unidad falla)."""
    return {"days": [{"date": date, "films": cartelera(date, stats)} for date in unit["dates"]]}


def snapshot(dates=None, days_ahead=None):
    """Crudo completo de la Cineteca: las tres sedes fijas de CDMX y la cartelera por día.

    `dates` fija los días a pedir (pruebas); si no, los próximos `days_ahead` (config.CINETECA_DAYS_AHEAD) desde hoy en
    la zona de referencia. Una sola unidad de captura con las tres sedes: si falla, `run.py` conserva el tablero anterior."""
    if dates is None:
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(config.PILOT_TIMEZONE)).date()
        n = days_ahead or config.CINETECA_DAYS_AHEAD
        dates = [(today + timedelta(days=i)).isoformat() for i in range(n)]
    unit = {"unit": "cineteca", "label": "Cineteca Nacional (CDMX)", "cinema_ids": sorted(SEDES), "dates": list(dates)}
    (record, data), = units.run_units([unit], _fetch)
    return {
        "chain": "cineteca",
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dates": list(dates),
        "sedes": SEDES,
        "days": data["days"] if data else [],
        "units": [record],
        "calls": record["calls"],
    }
