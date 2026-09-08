"""Cliente HTTP mínimo con reintentos, basado en urllib (sin dependencias)."""
import json
import time
import urllib.error
import urllib.request

from . import config


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class AuthError(ApiError):
    """401/403: casi siempre significa que la clave embebida rotó. Ver project.md."""


class RateLimited(ApiError):
    """429: la API pidió bajar el ritmo."""


def request_json(url, *, method="GET", headers=None, body=None, retries=None):
    retries = config.RETRIES if retries is None else retries
    hdrs = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    last_error = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT) as resp:
                raw = resp.read()
            time.sleep(config.PAUSE_BETWEEN_CALLS)
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            snippet = ""
            try:
                snippet = e.read(300).decode("utf-8", "replace")
            except Exception:
                pass
            if e.code in (401, 403):
                raise AuthError(f"HTTP {e.code} en {url}: {snippet}", e.code)
            if e.code == 429:
                last_error = RateLimited(f"HTTP 429 en {url}", 429)
                time.sleep(10 * (attempt + 1))
            elif 500 <= e.code < 600:
                last_error = ApiError(f"HTTP {e.code} en {url}: {snippet}", e.code)
            else:
                raise ApiError(f"HTTP {e.code} en {url}: {snippet}", e.code)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_error = ApiError(f"{type(e).__name__} en {url}: {e}")
        time.sleep(min(1.5 * (2 ** attempt), 30))
    raise last_error
