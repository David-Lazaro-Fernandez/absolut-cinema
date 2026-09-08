"""Configuración del scraper. Las claves pueden sobreescribirse por variable de entorno."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AC_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "snapshots.db"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
REQUEST_TIMEOUT = 60      # segundos por petición
RETRIES = 3               # reintentos ante 5xx / 429 / red
PAUSE_BETWEEN_CALLS = 0.15

# Plaza piloto: CDMX. Ambas cadenas operan en America/Mexico_City.
PILOT_TIMEZONE = "America/Mexico_City"

# --- Cinépolis (GraphQL, ver project.md) ---
CINEPOLIS_API_KEY = os.environ.get(
    "CINEPOLIS_API_KEY", "lQM6Mkvri1iHksKKCfpAiwGXq0YUZA7Nn6XAXRPr4i13LwXo"
)
CINEPOLIS_LOCATIONS_URL = "https://api-g.cinepolis.com/shared-services/locations/graphql"
CINEPOLIS_BILLBOARDS_URL = "https://api-g.cinepolis.com/v2/billboards/graphql"
CINEPOLIS_COUNTRY = "MX"
CINEPOLIS_CITY_ID = "cdmx"        # id de ciudad en locations (74 cines el 2026-09-07)
CINEPOLIS_BATCH_SIZE = 30         # la API rechaza más de 30 cines por llamada (error 105)
CINEPOLIS_PAGE_SIZE = 50

# --- Cinemex (REST, ver project.md sección Cinemex) ---
CINEMEX_BASE_URL = os.environ.get("CINEMEX_BASE_URL", "https://api.cinemex.com/rest/v2.37.2/")
CINEMEX_CONSUMER_KEY = os.environ.get("CINEMEX_CONSUMER_KEY", "XXQha7vz4kdvoMSdixhN")
CINEMEX_STATE_ID = 8              # "CDMX y Área Metropolitana"
# Áreas del estado 8 el 2026-09-07: Centro, Nor-oriente, Norte, Oriente, Poniente, Sur (87 cines).
CINEMEX_AREA_IDS = [15, 16, 17, 18, 19, 20]
CINEMEX_DAYS_AHEAD = 14           # días hacia adelante a pedir por área (cubre la semana de cine siguiente)

# Una función que desaparece del snapshot solo cuenta como "eliminada" si aún faltaban
# más de estos minutos para que empezara; si no, simplemente expiró.
REMOVED_GRACE_MINUTES = 30
