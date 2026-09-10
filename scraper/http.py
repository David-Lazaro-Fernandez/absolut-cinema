"""Cliente HTTP mínimo con reintentos, basado en urllib (sin dependencias)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class AuthError(ApiError):
    """401, o 403 con respuesta JSON de la API: casi siempre la clave embebida rotó. Ver project.md."""


class Blocked(ApiError):
    """403 con una página HTML en vez de JSON: el borde (Cloudflare) rechazó la IP de salida, no la clave.
    Visto el 2026-09-10 con `api-g.cinepolis.com` desde EC2 en us-east-1. No se reintenta: la regla no cambia
    entre intentos."""


class RateLimited(ApiError):
    """429: la API pidió bajar el ritmo."""


def request_json(url, *, method="GET", headers=None, body=None, retries=None):
    """GET/POST que devuelve el JSON decodificado. Reintenta 429, 408 y 5xx con espera progresiva."""
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    raw = _request(url, method=method, headers=hdrs, data=data, retries=retries, pause=config.PAUSE_BETWEEN_CALLS)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ApiError(f"JSON inválido en {url}: {e}")


def request_text(url, *, headers=None, retries=None, pause=None):
    """GET de una página HTML (sitios de consumo, no APIs) con los mismos reintentos. `pause` en segundos
    tras cada petición; por defecto `config.PAUSE_BETWEEN_CALLS`."""
    hdrs = {"Accept": "text/html", "Accept-Language": "es-MX,es;q=0.9"}
    if headers:
        hdrs.update(headers)
    return _request(url, method="GET", headers=hdrs, data=None, retries=retries,
                    pause=config.PAUSE_BETWEEN_CALLS if pause is None else pause).decode("utf-8", "replace")


MAX_REDIRECTS = 3
_OPENERS = {}


def _proxy_for(url):
    """URL del proxy de salida para `url`, o `None` si va directo (`config.EGRESS_PROXY` y `EGRESS_PROXY_HOSTS`)."""
    if not config.EGRESS_PROXY:
        return None
    host = urllib.parse.urlparse(url).hostname or ""
    return config.EGRESS_PROXY if host in config.EGRESS_PROXY_HOSTS else None


def _open(req, proxy):
    """`urlopen` directo, o a través de `proxy` (HTTP, con CONNECT para https) con un opener por proxy."""
    if proxy is None:
        return urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT)
    if proxy not in _OPENERS:
        _OPENERS[proxy] = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return _OPENERS[proxy].open(req, timeout=config.REQUEST_TIMEOUT)


def _forbidden_error(code, url, snippet):
    """Distingue un rechazo de la API (JSON, clave inválida) de un bloqueo del borde (página HTML)."""
    if code == 403 and snippet.lstrip().lower().startswith(("<!doctype", "<html")):
        return Blocked(f"HTTP 403 en {url}: bloqueo en el borde, el WAF devolvió una página HTML "
                       "en vez de JSON; la IP de salida no está permitida", code)
    return AuthError(f"HTTP {code} en {url}: {snippet}", code)


def _request(url, *, method, headers, data, retries, pause, redirects=0):
    retries = config.RETRIES if retries is None else retries
    hdrs = {"User-Agent": config.USER_AGENT}
    hdrs.update(headers)
    proxy = _proxy_for(url)
    last_error = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with _open(req, proxy) as resp:
                raw = resp.read()
            time.sleep(pause)
            return raw
        except urllib.error.HTTPError as e:
            snippet = ""
            try:
                snippet = e.read(300).decode("utf-8", "replace")
            except Exception:
                pass
            if e.code == 308 and e.headers.get("Location"):
                # urllib no sigue 308 (Rappi lo usa para llevar al slug canónico de la tienda, 2026-09-09).
                if redirects >= MAX_REDIRECTS:
                    raise ApiError(f"Demasiadas redirecciones en {url}", 308)
                target = urllib.parse.urljoin(url, e.headers["Location"])
                return _request(target, method=method, headers=headers, data=data, retries=retries, pause=pause,
                                redirects=redirects + 1)
            if e.code in (401, 403):
                raise _forbidden_error(e.code, url, snippet)
            if e.code == 429:
                last_error = RateLimited(f"HTTP 429 en {url}", 429)
                time.sleep(10 * (attempt + 1))
            elif e.code == 408 or 500 <= e.code < 600:
                # 408 "downstream duration timeout": el gateway de Cinépolis agotó el tiempo de su backend
                # (visto el 2026-09-08 en billboards). Se reintenta igual que un 5xx.
                last_error = ApiError(f"HTTP {e.code} en {url}: {snippet}", e.code)
            else:
                raise ApiError(f"HTTP {e.code} en {url}: {snippet}", e.code)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            via = f" (vía proxy {proxy})" if proxy else ""
            last_error = ApiError(f"{type(e).__name__} en {url}{via}: {e}")
        time.sleep(min(1.5 * (2 ** attempt), 30))
    raise last_error
