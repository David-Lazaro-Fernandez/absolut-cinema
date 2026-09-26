"""Convierte los crudos de cada cadena a un esquema común por función (fila = una función) y extrae la dimensión
de cines. Acepta las dos formas de crudo: la nacional (Cinemex por estado, Cinépolis con `cityId` por cine) y la del
piloto CDMX (Cinemex por área, Cinépolis con `city_id` a nivel captura), porque el archivo se reconstruye desde
los crudos viejos."""
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import config, states

COLUMNS = [
    "chain", "show_id", "cinema_id", "cinema_name", "lat", "lng", "city_id", "state_id", "state_code",
    "movie_id", "movie_title", "title_norm", "genre", "rating", "duration_min", "distributor",
    "date", "datetime_local", "datetime_utc", "screen", "language", "language_raw",
    "format", "experience", "premium_tier", "version_raw", "availability",
]
# Columnas de la dimensión de cines (tabla `cinema`): la llave geográfica más fina de cada API (`city_id`: Cinépolis
# slug de ciudad, Cinemex id de área), el estado de Cinemex (su agrupación de API), el estado de INEGI de ambas
# cadenas (`state_code`, `scraper/states.py`), la zona horaria IANA (solo la publica Cinépolis) y el vistaId de
# Cinépolis, que piden los planos y la dulcería.
CINEMA_COLUMNS = ["chain", "cinema_id", "name", "lat", "lng", "city_id", "state_id", "state_code", "timezone", "vista_id"]

# Campos cuyo cambio se considera "movida" (misma función, distinta hora o sala).
MOVE_FIELDS = ("datetime_local", "screen")
# Campos cuyo cambio se considera "cambiada" (idioma/formato/experiencia).
CHANGE_FIELDS = ("language", "format", "experience", "premium_tier", "movie_id")
# Todo lo que cuenta como cambio de estado de una función: lo usan el diff del scraper, la línea de tiempo del
# dashboard (analytics/history.py).
TRACKED_FIELDS = MOVE_FIELDS + CHANGE_FIELDS + ("availability",)


def norm_title(title):
    if not title:
        return ""
    s = unicodedata.normalize("NFKD", title)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        m = re.search(r"\d+", str(value or ""))
        return int(m.group()) if m else None


def cinemex_duration(text):
    """'2h 55m' -> 175."""
    if not text:
        return None
    h = re.search(r"(\d+)\s*h", text)
    m = re.search(r"(\d+)\s*m", text)
    if not h and not m:
        return to_int(text)
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def cinepolis_language(code):
    code = (code or "").upper()
    if code.startswith("SUB"):
        return "subtitled"
    if code.startswith("ESP"):
        return "spanish"
    if code.startswith("ORIG") or code.startswith("ING") or code.startswith("ENG"):
        return "original"
    return "other"


def _utc(local, offset_or_tz):
    """'YYYY-MM-DDTHH:MM:SS' + ('-06:00' | zona IANA) → ISO en UTC con '+00:00'; None si algo no se puede leer."""
    if not local or not offset_or_tz:
        return None
    try:
        if offset_or_tz[0] in "+-":
            dt = datetime.fromisoformat(local[:19] + offset_or_tz)
        else:
            dt = datetime.fromisoformat(local[:19]).replace(tzinfo=ZoneInfo(offset_or_tz))
    except (ValueError, KeyError):
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def cinepolis_cinemas(raw):
    """Dimensión de cines desde el crudo de Cinépolis (una fila por cine, columnas CINEMA_COLUMNS)."""
    city = raw.get("city_id")   # crudo del piloto: la ciudad iba a nivel captura
    for c in raw.get("cinemas", []):
        yield {"chain": "cinepolis", "cinema_id": c["id"], "name": c.get("name"), "lat": c.get("lat"), "lng": c.get("lng"),
               "city_id": c.get("cityId") or city, "state_id": None,
               "state_code": states.state_code("cinepolis", c["id"], c.get("cityId") or city), "timezone": c.get("timezone") or None,
               "vista_id": str(c["vistaId"]) if c.get("vistaId") is not None else None}


def cinepolis_rows(raw):
    cinemas = {c["cinema_id"]: c for c in cinepolis_cinemas(raw)}
    for bb in raw.get("billboards", []):
        movie = raw.get("movies", {}).get(bb["movie_id"], {})
        genre = movie.get("genre") or []
        for sched in bb.get("schedules", []):
            slug = sched.get("cinemaId")
            cinema = cinemas.get(slug, {})
            tz = cinema.get("timezone") or raw.get("timezone") or config.PILOT_TIMEZONE
            tier = "vip" if "-vip-" in f"-{slug}-" else "traditional"
            for day in sched.get("dates", []):
                for lang in day.get("languages", []):
                    for st in lang.get("showtimes", []):
                        fmt = (st.get("format") or {}).get("name")
                        exp = (st.get("experience") or {}).get("name")
                        local = (st.get("datetime") or "")[:19]
                        yield {
                            "chain": "cinepolis",
                            # El sessionId de Vista solo es único dentro de cada cine (914 colisiones
                            # entre cines de CDMX el 2026-09-08), por eso la identidad lleva el cine.
                            "show_id": f"{slug}:{st['sessionId']}",
                            "cinema_id": slug,
                            "cinema_name": cinema.get("name"),
                            "lat": cinema.get("lat"), "lng": cinema.get("lng"),
                            "city_id": cinema.get("city_id"), "state_id": None,
                            "state_code": cinema.get("state_code") or states.state_code("cinepolis", slug, cinema.get("city_id")),
                            "movie_id": bb["movie_id"],
                            "movie_title": movie.get("name"),
                            "title_norm": norm_title(movie.get("name")),
                            "genre": "|".join(genre) if isinstance(genre, list) else str(genre),
                            "rating": movie.get("rating"),
                            "duration_min": to_int(movie.get("length")),
                            "distributor": movie.get("distributor"),
                            "date": day.get("date"),
                            "datetime_local": local,
                            # La API da la hora local del cine sin offset; la zona viene del catálogo de cines.
                            "datetime_utc": _utc(local, tz),
                            "screen": str(st.get("screen")) if st.get("screen") is not None else None,
                            "language": cinepolis_language(lang.get("language")),
                            "language_raw": lang.get("language"),
                            "format": fmt,
                            "experience": exp,
                            "premium_tier": tier,
                            "version_raw": " ".join(x for x in (fmt, exp) if x) or None,
                            "availability": st.get("availability") or None,
                        }


CINEMEX_NON_EXPERIENCE = {"platinum", "premium", "traditional", "lang_sub", "lang_es", "lang_esp", "lang_orig", "2d", "3d", "v3d"}


def _first_str(*values):
    for v in values:
        if v is not None and str(v) != "":
            return str(v)
    return None


def _cinemex_payloads(raw):
    """Payloads de cartelera (uno por día) del crudo, venga por estado (nacional) o por área (piloto)."""
    for unit in raw.get("states") or raw.get("areas") or []:
        for day in unit.get("days", []):
            yield day["data"]


def _cinemex_cinema(c):
    area, state = c.get("area") or {}, c.get("state") or {}
    city_id = str(area["id"]) if area.get("id") is not None else None
    return {"chain": "cinemex", "cinema_id": str(c["id"]), "name": c.get("name"), "lat": c.get("lat"), "lng": c.get("lng"),
            "city_id": city_id, "state_id": str(state["id"]) if state.get("id") is not None else None,
            "state_code": states.state_code("cinemex", c["id"], city_id), "timezone": None, "vista_id": None}


def cinemex_cinemas(raw):
    """Dimensión de cines desde el crudo de Cinemex (una fila por cine, columnas CINEMA_COLUMNS)."""
    seen = set()
    for payload in _cinemex_payloads(raw):
        for c in payload.get("cinemas") or []:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            yield _cinemex_cinema(c)


def cinemex_rows(raw):
    for payload in _cinemex_payloads(raw):
        for c in payload.get("cinemas") or []:
            place = _cinemex_cinema(c)
            for m in c.get("movies") or []:
                info = m.get("info") or {}
                genre = info.get("genre") or []
                for v in m.get("versions") or []:
                    types = [t.lower() for t in (v.get("type") or [])]
                    if "lang_sub" in types:
                        language = "subtitled"
                    elif "lang_orig" in types:
                        language = "original"
                    else:
                        language = "spanish"
                    tier = "platinum" if "platinum" in types else "premium" if "premium" in types else "traditional"
                    fmt = "3D" if ("3d" in types or "v3d" in types) else "2D"
                    exp = "|".join(t for t in types if t not in CINEMEX_NON_EXPERIENCE) or None
                    for s in v.get("sessions") or []:
                        full = s.get("datetime") or ""
                        dt = full[:19]
                        yield {
                            "chain": "cinemex",
                            "show_id": str(s["id"]),
                            "cinema_id": place["cinema_id"],
                            "cinema_name": c.get("name"),
                            "lat": c.get("lat"), "lng": c.get("lng"),
                            "city_id": place["city_id"], "state_id": place["state_id"], "state_code": place["state_code"],
                            "movie_id": str(m["id"]),
                            "movie_title": m.get("name"),
                            "title_norm": norm_title(m.get("name")),
                            "genre": "|".join(genre) if isinstance(genre, list) else str(genre),
                            "rating": info.get("rating"),
                            "duration_min": cinemex_duration(info.get("duration")),
                            "distributor": info.get("distributor"),
                            "date": dt[:10],
                            "datetime_local": dt,
                            # `datetime` trae el offset del cine ('2026-09-10T13:00:00-06:00').
                            "datetime_utc": _utc(dt, full[19:] or None),
                            # 2026-09-08 ~10:30 CDMX: Cinemex adelgazó el payload de sesión y `screen_number`
                            # pasó a llamarse `auditorium_number` (mismo valor, ahora string).
                            "screen": _first_str(s.get("screen_number"), s.get("auditorium_number")),
                            "language": language,
                            "language_raw": v.get("label"),
                            "format": fmt,
                            "experience": exp,
                            "premium_tier": tier,
                            "version_raw": v.get("label"),
                            "availability": s.get("availability") or None,
                        }


def cineteca_language(title):
    """Idioma desde el título: la Cineteca marca el doblaje/subtitulaje con sufijos (DOB/DUB, SUB); sin marca es
    lengua original (cine de autor), que se deja como `other` porque el endpoint no distingue original de local."""
    t = (title or "").upper()
    if "SUB" in t:
        return "subtitled"
    if "DOB" in t or "DUB" in t:
        return "spanish"
    return "other"


def cineteca_cinemas(raw):
    """Dimensión de cines desde el crudo de la Cineteca (una fila por sede, columnas CINEMA_COLUMNS). Las tres sedes
    son fijas y de CDMX; `cinema_id = city_id = vista_id = codigo_sede` (el cinemacode que pide el plano de Vista)."""
    for code, s in sorted((raw.get("sedes") or {}).items()):
        yield {"chain": "cineteca", "cinema_id": code, "name": s.get("name"), "lat": s.get("lat"), "lng": s.get("lng"),
               "city_id": code, "state_id": None, "state_code": states.state_code("cineteca", code, code),
               "timezone": config.PILOT_TIMEZONE, "vista_id": code}


def cineteca_rows(raw):
    place_by_id = {c["cinema_id"]: c for c in cineteca_cinemas(raw)}
    tz = config.PILOT_TIMEZONE
    for day in raw.get("days") or []:
        date = day.get("date")
        for film in day.get("films") or []:
            title = film.get("titulo")
            for sede in film.get("sedes") or []:
                code = sede.get("codigo_sede")
                place = place_by_id.get(code, {})
                for h in sede.get("horarios") or []:
                    session_id = h.get("session_id")
                    local = f"{date}T{h.get('hora')}:00" if date and h.get("hora") else None
                    yield {
                        "chain": "cineteca",
                        # El sessionId de Vista solo es único dentro de cada sede, igual que en Cinépolis: la identidad
                        # lleva la sede.
                        "show_id": f"{code}:{session_id}",
                        "cinema_id": code,
                        "cinema_name": place.get("name"),
                        "lat": place.get("lat"), "lng": place.get("lng"),
                        "city_id": code, "state_id": None, "state_code": place.get("state_code"),
                        "movie_id": film.get("film_id"),
                        "movie_title": title,
                        "title_norm": norm_title(title),
                        "genre": None,
                        "rating": film.get("clasificacion"),
                        "duration_min": None,
                        "distributor": None,
                        "date": date,
                        "datetime_local": local,
                        "datetime_utc": _utc(local, tz),
                        # La cartelera no trae la sala; se llena desde el plano de asientos (scraper/sample.py).
                        "screen": None,
                        "language": cineteca_language(title),
                        "language_raw": None,
                        "format": "2D",
                        "experience": None,
                        "premium_tier": "traditional",
                        "version_raw": None,
                        "availability": None,
                    }


_ROWS = {"cinepolis": cinepolis_rows, "cinemex": cinemex_rows, "cineteca": cineteca_rows}
_CINEMAS = {"cinepolis": cinepolis_cinemas, "cinemex": cinemex_cinemas, "cineteca": cineteca_cinemas}


def rows(chain, raw):
    seen = {}
    for r in _ROWS[chain](raw):
        seen.setdefault(r["show_id"], r)   # una fila por función aunque aparezca dos veces
    return list(seen.values())


def cinemas(chain, raw):
    """Dimensión de cines de un crudo: lista de dicts con CINEMA_COLUMNS, una por cine, ordenada por `cinema_id`."""
    return sorted(_CINEMAS[chain](raw), key=lambda c: c["cinema_id"])


def format_bucket(row):
    """premium | large | 3d4d | traditional. Misma regla que el CASE de analytics/queries.py: si
    cambia una, cambiar la otra. La sala manda sobre la tecnología, y la tecnología sobre el 3D."""
    tier = (row.get("premium_tier") or "").lower()
    exp = (row.get("experience") or "")
    if tier in ("premium", "platinum", "vip") or exp in ("confort", "SP"):
        return "premium"
    if exp.lower() in ("imax", "xe", "screenx", "xescreenx", "dolby_atmos", "jumbo", "led"):
        return "large"
    if (row.get("format") or "") == "3D" or exp.lower() in ("v4d", "4dx"):
        return "3d4d"
    return "traditional"
