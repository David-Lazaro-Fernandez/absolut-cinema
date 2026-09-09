"""Convierte los crudos de cada cadena a un esquema común por función (fila = una función)."""
import re
import unicodedata

COLUMNS = [
    "chain", "show_id", "cinema_id", "cinema_name", "lat", "lng",
    "movie_id", "movie_title", "title_norm", "genre", "rating", "duration_min", "distributor",
    "date", "datetime_local", "screen", "language", "language_raw",
    "format", "experience", "premium_tier", "version_raw", "availability",
]

# Campos cuyo cambio se considera "movida" (misma función, distinta hora o sala).
MOVE_FIELDS = ("datetime_local", "screen")
# Campos cuyo cambio se considera "cambiada" (idioma/formato/experiencia).
CHANGE_FIELDS = ("language", "format", "experience", "premium_tier", "movie_id")
# Todo lo que cuenta como cambio de estado de una función: lo usan el diff del scraper, la línea de tiempo del
# dashboard (analytics/history.py) y las versiones de estado del archivo histórico (sync/).
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


def cinepolis_rows(raw):
    cinemas = {c["id"]: c for c in raw.get("cinemas", [])}
    for bb in raw.get("billboards", []):
        movie = raw.get("movies", {}).get(bb["movie_id"], {})
        genre = movie.get("genre") or []
        for sched in bb.get("schedules", []):
            slug = sched.get("cinemaId")
            cinema = cinemas.get(slug, {})
            tier = "vip" if "-vip-" in f"-{slug}-" else "traditional"
            for day in sched.get("dates", []):
                for lang in day.get("languages", []):
                    for st in lang.get("showtimes", []):
                        fmt = (st.get("format") or {}).get("name")
                        exp = (st.get("experience") or {}).get("name")
                        yield {
                            "chain": "cinepolis",
                            # El sessionId de Vista solo es único dentro de cada cine (914 colisiones
                            # entre cines de CDMX el 2026-09-08), por eso la identidad lleva el cine.
                            "show_id": f"{slug}:{st['sessionId']}",
                            "cinema_id": slug,
                            "cinema_name": cinema.get("name"),
                            "lat": cinema.get("lat"), "lng": cinema.get("lng"),
                            "movie_id": bb["movie_id"],
                            "movie_title": movie.get("name"),
                            "title_norm": norm_title(movie.get("name")),
                            "genre": "|".join(genre) if isinstance(genre, list) else str(genre),
                            "rating": movie.get("rating"),
                            "duration_min": to_int(movie.get("length")),
                            "distributor": movie.get("distributor"),
                            "date": day.get("date"),
                            "datetime_local": (st.get("datetime") or "")[:19],
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


def cinemex_rows(raw):
    for area in raw.get("areas", []):
        for day in area.get("days", []):
            for c in day["data"].get("cinemas") or []:
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
                            dt = (s.get("datetime") or "")[:19]
                            yield {
                                "chain": "cinemex",
                                "show_id": str(s["id"]),
                                "cinema_id": str(c["id"]),
                                "cinema_name": c.get("name"),
                                "lat": c.get("lat"), "lng": c.get("lng"),
                                "movie_id": str(m["id"]),
                                "movie_title": m.get("name"),
                                "title_norm": norm_title(m.get("name")),
                                "genre": "|".join(genre) if isinstance(genre, list) else str(genre),
                                "rating": info.get("rating"),
                                "duration_min": cinemex_duration(info.get("duration")),
                                "distributor": info.get("distributor"),
                                "date": dt[:10],
                                "datetime_local": dt,
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


def rows(chain, raw):
    gen = cinepolis_rows(raw) if chain == "cinepolis" else cinemex_rows(raw)
    seen = {}
    for r in gen:
        seen.setdefault(r["show_id"], r)   # una fila por función aunque aparezca dos veces
    return list(seen.values())


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
