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
CINEPOLIS_TICKET_URL = "https://api-g.cinepolis.com/v1/ticket/graphql"              # planos y boletos (verificado 2026-09-08)
# Dulcería: lo consulta el microfrontend foods-menu-mf.cinepolis.com con la misma x-apikey (verificado 2026-09-08).
CINEPOLIS_CONCESSIONS_URL = "https://api-g.cinepolis.com/v1/fab-struct-concession/graphql"
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

# Muestreo de asientos (scraper/sample.py). La API de Vista detrás de Cinépolis responde errores
# transitorios (116, 101305) si se le pide plano tras plano sin pausa.
SAMPLE_PAUSE = 0.6        # segundos entre planos
SAMPLE_BACKOFF = 5        # segundos tras un error

# Captura de cartelera: tres veces al día (decisión del cliente, 2026-09-08). Hora local de la plaza.
# Los planos de asientos siguen cada 15 min porque dependen de la hora de cada función.
SNAPSHOT_HOURS = tuple(os.environ.get("AC_SNAPSHOT_HOURS", "07:30,13:30,20:30").split(","))

# Planos post-inicio (sample --post-start): la asistencia final de cada función. El plano existe ~2.5 h después
# del inicio, así que una corrida por hora con ventana de 15 a 75 min cubre todas las funciones (decisión 2026-09-09:
# solo post-inicio, sin la lectura de preventa a T−60, que aportaba poco).
POST_START_AFTER_MIN = 45
POST_START_TOLERANCE_MIN = 30

# Dulcería de Cinépolis (sample --concessions): un menú completo por cine, renovado cada tantos días.
CONCESSIONS_REFRESH_DAYS = 7

# Dulcería a domicilio (scraper/delivery.py). Rappi y DiDi Food sirven el HTML con precios del lado del
# servidor; Uber Eats queda fuera porque sus términos prohíben la extracción. Una petición cada DELIVERY_PAUSE s:
# son sitios de consumo, no APIs, y no hay motivo para ir más rápido.
DELIVERY_PAUSE = 1.5
DELIVERY_REFRESH_DAYS = 7
RAPPI_BASE_URL = os.environ.get("RAPPI_BASE_URL", "https://www.rappi.com.mx")
RAPPI_CITY = "ciudad-de-mexico"
# Listado por marca /{ciudad}/restaurantes/delivery/{brandId}-{slug} (ids vistos el 2026-09-09).
RAPPI_BRANDS = {"cinemex": (51760, "cinemex"), "cinepolis": (96681, "cinepolis-tradicional")}
DIDI_BASE_URL = os.environ.get("DIDI_BASE_URL", "https://web.didiglobal.com")
DIDI_CITY = "ciudad-de-mexico-cdmx"
DIDI_CATEGORY = "pasaboca"        # categoría de botanas: ahí lista los cines (2026-09-09)
DIDI_MAX_PAGES = 60

# --- Archivo histórico en PostgreSQL (sync/; ver docs/postgres-esquema.md) ---
# El sync corre en el venv (psycopg); el scraper nunca lo importa. En desarrollo apunta al Postgres de
# deploy/docker-compose.dev.yml; en el servidor, AC_PG_DSN va en /etc/absolut-cinema.env.
PG_DSN = os.environ.get("AC_PG_DSN", "postgresql://absolut:absolut-dev@localhost:5433/absolut_cinema")
BACKUP_BUCKET = os.environ.get("BACKUP_BUCKET")            # si existe, snapshot.raw_path en Postgres apunta al bucket
SYNC_STATUS_PATH = LOG_DIR / "sync_status.json"            # lo escribe el sync y lo lee scraper.health (sin psycopg)
SYNC_MAX_AGE_MIN = 90                                       # el sync corre cada 30 min; más de esto es un problema
SNAPSHOT_STALE_HOURS = 2                                    # snapshot sin finish_snapshot más viejo que esto: se da por fallido
