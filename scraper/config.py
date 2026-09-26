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
# Reintentos de una unidad de captura completa (un estado de Cinemex, un lote de Cinépolis) que falló aun con los
# reintentos por petición; se hacen al final de la pasada, cuando ya corrieron las demás (scraper/units.py).
UNIT_RETRIES = 1
PAUSE_BETWEEN_CALLS = 0.15
# Pausa por host, cuando difiere de la general. Cinépolis no ha devuelto un 429 nunca, pero la captura nacional medida el
# 2026-09-11 iba a 90 llamadas/min hacia api-g.cinepolis.com y el pase de butacas de :50 suma al mismo host; el límite
# habitual de una API pública es 100/min y no queremos descubrirlo. Con 0.6 s la captura sola queda en ~55/min (975
# llamadas en ~17 min) y con el pase de butacas encima en ~70/min. Cinemex sirve desde caché y va a 50/min: se queda.
PAUSE_BY_HOST = {"api-g.cinepolis.com": float(os.environ.get("AC_CINEPOLIS_PAUSE", "0.6"))}

# Salida por proxy para los hosts que rechazan la IP del servidor. El WAF de Cloudflare de api-g.cinepolis.com
# bloquea los rangos de AWS por ASN (verificado 2026-09-10 desde EC2 en us-east-1: 403 directo, 200 saliendo por
# Cloudflare WARP). En el servidor AC_EGRESS_PROXY apunta al proxy HTTP local que reenvía al SOCKS5 de WARP
# (deploy/README.md); vacío = todo sale directo, como en la Mac. Solo los hosts listados pasan por el proxy.
EGRESS_PROXY = os.environ.get("AC_EGRESS_PROXY", "")
EGRESS_PROXY_HOSTS = tuple(h.strip() for h in os.environ.get("AC_EGRESS_PROXY_HOSTS", "api-g.cinepolis.com").split(",")
                           if h.strip())

# Zona horaria de referencia: la del dashboard, de "hoy" y de las horas programadas. Cada función lleva además su
# hora UTC (`datetime_utc`), porque México tiene siete zonas (Tijuana, Hermosillo, Cancún…) y "ya empezó" se decide
# con esa, no con la de referencia.
PILOT_TIMEZONE = "America/Mexico_City"


def _csv(name):
    """Lista desde una variable de entorno separada por comas; vacía si no está o está en blanco."""
    return tuple(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())


# Alcance de la captura de cartelera: nacional por defecto. Para acotar (desarrollo, una plaza de prueba):
# AC_CINEPOLIS_CITIES=cdmx AC_CINEMEX_STATES=8.
CINEPOLIS_CITIES = _csv("AC_CINEPOLIS_CITIES")     # slugs de ciudad de Cinépolis (154 el 2026-09-11); vacío = todas
CINEMEX_STATES = tuple(int(x) for x in _csv("AC_CINEMEX_STATES"))   # ids de estado de Cinemex (31); vacío = todos
# Plazas cuyas funciones entran al muestreo de planos de asientos (post-inicio, aforo, preventa). Claves de
# scraper/plazas.py. Decisión 2026-09-11: los planos no se censan a nivel nacional; se acotan a las plazas que pida
# el cliente, elegidas con el registro inicial de funciones por plaza.
SEATS_PLAZAS = _csv("AC_SEATS_PLAZAS") or ("cdmx",)

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
CINEPOLIS_BATCH_SIZE = 30         # la API rechaza más de 30 cines por llamada (error 105; confirmado 2026-09-11 con 31 y 40)
CINEPOLIS_PAGE_SIZE = 50

# --- Cinemex (REST, ver project.md sección Cinemex) ---
CINEMEX_BASE_URL = os.environ.get("CINEMEX_BASE_URL", "https://api.cinemex.com/rest/v2.38/")
CINEMEX_CONSUMER_KEY = os.environ.get("CINEMEX_CONSUMER_KEY", "XXQha7vz4kdvoMSdixhN")
# La unidad de consulta de cartelera es el estado (`cinemas/state/{id}/movies/`, 31 estados el 2026-09-11); CDMX es el 8.
CINEMEX_DAYS_AHEAD = 14           # días hacia adelante a pedir por estado (cubre la semana de cine siguiente)
# Estados de Cinemex que se descargan a la vez. En serie iba a ~50 llamadas/min y 9 min la captura nacional; la API
# sirve desde caché y nunca ha devuelto 429. Cada hilo respeta PAUSE_BETWEEN_CALLS. Cinépolis sigue en serie: su
# ritmo lo fija PAUSE_BY_HOST, no el número de hilos.
CINEMEX_WORKERS = int(os.environ.get("AC_CINEMEX_WORKERS", "3"))

# --- Cineteca Nacional (tercera cadena, ver project.md) ---
# Cine independiente de CDMX (tres sedes). La cartelera es un JSON público sin clave; la ocupación sale del plano de
# asientos de Vista (mismo motor que Cinépolis) con un token embebido en la app oficial, como CINEPOLIS_API_KEY.
# No entra a las comparaciones head-to-head Cinemex↔Cinépolis: se captura aparte (decisión 2026-09-26).
CINETECA_CARTELERA_URL = os.environ.get("CINETECA_CARTELERA_URL", "https://www.cinetecanacional.net/obtener_cartelera.php")
CINETECA_VISTA_BASE_URL = os.environ.get("CINETECA_VISTA_BASE_URL", "https://rbvfcn.cinetecanacional.net/WSVistaWebClient")
CINETECA_CONNECT_TOKEN = os.environ.get("CINETECA_CONNECT_TOKEN", "00Hce1yZxXdQtA9ZgvQR69ElXrBgLT")
CINETECA_DAYS_AHEAD = 14           # días hacia adelante a pedir (cubre la semana de cine siguiente, como Cinemex)

# Una función que desaparece del snapshot solo cuenta como "eliminada" si aún faltaban
# más de estos minutos para que empezara; si no, simplemente expiró.
REMOVED_GRACE_MINUTES = 30

# Muestreo de asientos (scraper/sample.py). La API de Vista detrás de Cinépolis responde errores
# transitorios (116, 101305) si se le pide plano tras plano sin pausa.
SAMPLE_PAUSE = 0.6        # segundos entre planos (por hilo)
SAMPLE_BACKOFF = 5        # segundos tras un error
# Hilos del pase de aforo (`sample --capacity`), todos desde la misma IP y cada uno con su SAMPLE_PAUSE. 1 en los
# timers; la pasada nacional única se lanzó a mano con 3 (2026-09-12) para bajar de ~2 h a ~40 min por cadena. La
# escritura en SQLite sigue en el hilo principal.
SAMPLE_WORKERS = int(os.environ.get("AC_SAMPLE_WORKERS", "1"))

# Planos post-inicio (sample --post-start): la asistencia final de cada función. El plano existe ~2.5 h después
# del inicio, así que una corrida por hora con ventana de 15 a 75 min cubre todas las funciones (decisión 2026-09-09:
# solo post-inicio, sin la lectura de preventa a T−60, que aportaba poco).
POST_START_AFTER_MIN = 45
POST_START_TOLERANCE_MIN = 30

# Preventas de Cinemex (scraper/presale.py). Los títulos son los de la landing `preventas` de `GET landings/` y el
# estreno sale de `upcoming`, incrustado en el HTML del sitio (verificado 2026-09-25). Cada título lleva un panel fijo
# de funciones que se releen a diario hasta que empiezan: da la curva de venta (decisión 2026-09-25: 30 por título).
CINEMEX_SITE_URL = os.environ.get("CINEMEX_SITE_URL", "https://cinemex.com/landing/preventas/peliculas/")
PRESALE_LANDING_SLUG = "preventas"
PRESALE_PANEL_PER_TITLE = int(os.environ.get("AC_PRESALE_PANEL", "30"))

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

SNAPSHOT_STALE_HOURS = 2                                    # snapshot sin finish_snapshot más viejo que esto: se da por fallido

# --- Acceso al dashboard (auth/) ---
# Cuentas, sesiones, enlaces y auditoría en su propia base SQLite: la escribe solo auth/ (dashboard y auth.cli), nunca
# la captura; snapshots.db sigue siendo solo de la captura (decisión 2026-09-25: sin Postgres ni RDS).
APP_DB_PATH = Path(os.environ.get("AC_APP_DB", DATA_DIR / "app.db"))
MAIL_BACKEND = os.environ.get("AC_MAIL_BACKEND", "console")      # console: escribe data/logs/mail.log; ses: Amazon SES
MAIL_FROM = os.environ.get("AC_MAIL_FROM", "Absolut Cinema <no-responder@localhost>")   # en SES, identidad verificada
BASE_URL = os.environ.get("AC_BASE_URL", "http://localhost:8501").rstrip("/")            # base de los enlaces del correo
MAIL_LOG_PATH = LOG_DIR / "mail.log"
