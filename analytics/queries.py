"""Consultas sobre current_showtime, event y snapshot.

Ventana de análisis: un rango de fechas [d0, d1] en hora local de la plaza (la que guarda el
scraper en datetime_local). La unidad natural es la **semana de cine** (jueves a miércoles),
que es lo que ambas cadenas publican completo.

Comparación justa del día en curso: Cinépolis borra cada función cuando empieza y Cinemex la
conserva unas horas más. Por eso, si la ventana incluye hoy, solo se cuentan funciones que aún
no han empezado en ambas cadenas (`from_now`, activado por defecto).

Todas las medidas comparables son **shares** (% de la programación de cada cadena), nunca
absolutos, porque cada cadena tiene distinto número de cines y salas. Denominador: funciones.
Cuando exista aforo por sala el denominador pasará a butacas ofertadas."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from scraper import config

from .db import rows
from .labels import FULL_DAY, PRIME_START_HOUR, SLOTS


def now_local(tz=config.PILOT_TIMEZONE):
    return datetime.now(ZoneInfo(tz))


def today(tz=config.PILOT_TIMEZONE):
    return now_local(tz).strftime("%Y-%m-%d")


def cinema_week(iso):
    """(jueves, miércoles) de la semana de cine que contiene la fecha."""
    d = date.fromisoformat(iso)
    thu = d - timedelta(days=(d.weekday() - 3) % 7)
    return thu.isoformat(), (thu + timedelta(days=6)).isoformat()


_HOUR = "CAST(substr(datetime_local, 12, 2) AS INTEGER)"


def is_full_day(hours):
    """True si el filtro de franja no recorta nada (None o (0, 24))."""
    return hours is None or tuple(hours) == FULL_DAY


def _window(d0, d1=None, from_now=True, hours=None):
    """WHERE para [d0, d1]; si incluye hoy y from_now, excluye lo que ya empezó. `hours=(h0, h1)` deja solo
    las funciones que empiezan entre esas horas (h1 exclusiva); con None o (0, 24) no añade nada.
    Devuelve (sql, params, hhmm_desde | None)."""
    d0 = d0 or today()
    d1 = d1 or d0
    hhmm = None
    if from_now and d0 <= today() <= d1:
        now = now_local()
        where, params, hhmm = "date BETWEEN ? AND ? AND datetime_local >= ?", [d0, d1, now.strftime("%Y-%m-%dT%H:%M:%S")], now.strftime("%H:%M")
    else:
        where, params = "date BETWEEN ? AND ?", [d0, d1]
    if not is_full_day(hours):
        where += f" AND {_HOUR} >= ? AND {_HOUR} < ?"
        params += [int(hours[0]), int(hours[1])]
    return where, params, hhmm


# Cubetas de formato en SQL, para que el dashboard y un API vean lo mismo.
_FORMAT_CASE = """CASE
    WHEN premium_tier IN ('premium', 'platinum', 'vip') OR experience IN ('confort', 'SP') THEN 'premium'
    WHEN lower(experience) IN ('imax', 'xe', 'screenx', 'xescreenx', 'dolby_atmos', 'jumbo', 'led') THEN 'large'
    WHEN format = '3D' OR lower(experience) IN ('v4d', '4dx') THEN '3d4d'
    ELSE 'traditional' END"""
_LANG_CASE = "CASE WHEN language = 'subtitled' THEN 'subtitled' ELSE 'spanish' END"
_WEEKDAY = "(CAST(strftime('%w', date) AS INTEGER) + 6) % 7"      # 0 = lunes
_IS_PRIME = f"({_WEEKDAY} >= 4 AND {_HOUR} >= {PRIME_START_HOUR})"


def snapshot_health(conn, limit=20):
    """Últimos snapshots por cadena con duración, funciones y errores."""
    return rows(conn, """
        SELECT id, chain, taken_at, finished_at, ok, n_shows, n_cinemas, n_events, calls,
               duration_s, error
        FROM snapshot ORDER BY id DESC LIMIT ?""", (limit,))


def coverage(conn):
    """Funciones publicadas por fecha y cadena. Sirve para saber qué semanas están completas."""
    return rows(conn, """
        SELECT date, SUM(chain = 'cinemex') cinemex, SUM(chain = 'cinepolis') cinepolis
        FROM current_showtime GROUP BY date ORDER BY date""")


def kpis(conn, d0=None, d1=None, from_now=True, hours=None):
    """Por cadena: cines, funciones, funciones por cine y día, películas, % subtituladas,
    % en horario prime (vie–dom desde 6 P.M.) y % de 6 P.M. en adelante cualquier día."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    return rows(conn, f"""
        SELECT chain,
               COUNT(DISTINCT cinema_id)                                   cinemas,
               COUNT(*)                                                    shows,
               COUNT(DISTINCT movie_id)                                    movies,
               COUNT(DISTINCT date)                                        days,
               ROUND(100.0 * SUM(language = 'subtitled') / COUNT(*), 1)   pct_subtitled,
               ROUND(1.0 * COUNT(*) / COUNT(DISTINCT cinema_id) / COUNT(DISTINCT date), 1) shows_per_cinema,
               ROUND(100.0 * SUM({_IS_PRIME}) / COUNT(*), 1)              pct_prime,
               ROUND(100.0 * SUM({_HOUR} >= {PRIME_START_HOUR}) / COUNT(*), 1) pct_evening,
               SUM({_WEEKDAY} >= 4)                                        weekend_shows
        FROM current_showtime WHERE {where} GROUP BY chain ORDER BY chain""", params)


kpis_today = kpis   # compatibilidad


def showtimes_by_slot(conn, d0=None, d1=None, from_now=True, hours=None):
    """Funciones por franja horaria y cadena. Claves de franja en labels.SLOTS."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    cols = ",\n".join(f"SUM({_HOUR} BETWEEN {lo} AND {hi - 1}) {key}" for key, lo, hi, _ in SLOTS)
    return rows(conn, f"""
        SELECT chain, {cols}, COUNT(*) total, COUNT(DISTINCT cinema_id) cinemas
        FROM current_showtime WHERE {where} GROUP BY chain ORDER BY chain""", params)


def heatmap_day_slot(conn, d0=None, d1=None, from_now=True, hours=None):
    """Share de la programación de cada cadena por día de la semana y franja (en % del total de
    la cadena en la ventana) y la diferencia en puntos (positivo = Cinemex pone más)."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    slot_case = "CASE " + " ".join(f"WHEN {_HOUR} BETWEEN {lo} AND {hi - 1} THEN '{key}'" for key, lo, hi, _ in SLOTS) + " END"
    return rows(conn, f"""
        WITH base AS (SELECT chain, {_WEEKDAY} weekday, {slot_case} slot FROM current_showtime WHERE {where}),
             tot AS (SELECT chain, COUNT(*) n FROM base GROUP BY chain),
             cell AS (SELECT chain, weekday, slot, COUNT(*) n FROM base GROUP BY chain, weekday, slot)
        SELECT c.weekday, c.slot,
               SUM(CASE WHEN c.chain = 'cinemex'   THEN c.n END)                                         shows_cinemex,
               SUM(CASE WHEN c.chain = 'cinepolis' THEN c.n END)                                         shows_cinepolis,
               ROUND(100.0 * SUM(CASE WHEN c.chain = 'cinemex'   THEN c.n END) / (SELECT n FROM tot WHERE chain = 'cinemex'), 1)   share_cinemex,
               ROUND(100.0 * SUM(CASE WHEN c.chain = 'cinepolis' THEN c.n END) / (SELECT n FROM tot WHERE chain = 'cinepolis'), 1) share_cinepolis
        FROM cell c GROUP BY c.weekday, c.slot ORDER BY c.weekday, c.slot""", params)


def movies_by_chain(conn, d0=None, d1=None, limit=60, from_now=True, hours=None):
    """Funciones por película y cadena, emparejadas por title_norm, con la participación (% de la
    programación de cada cadena) y la diferencia en puntos (`gap_pp`, positivo = Cinemex apuesta
    más). La tabla de equivalencias entre cadenas refinará el emparejamiento."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    return rows(conn, f"""
        WITH base AS (SELECT * FROM current_showtime WHERE {where}),
             n_cin AS (SELECT chain, COUNT(DISTINCT cinema_id) n, COUNT(*) shows FROM base GROUP BY chain)
        SELECT title_norm,
               COALESCE(MAX(CASE WHEN b.chain = 'cinemex'   THEN movie_title END),
                        MAX(CASE WHEN b.chain = 'cinepolis' THEN movie_title END)) title,
               MAX(CASE WHEN b.chain = 'cinemex'   THEN movie_title END)  title_cinemex,
               MAX(CASE WHEN b.chain = 'cinepolis' THEN movie_title END)  title_cinepolis,
               SUM(b.chain = 'cinemex')                                   shows_cinemex,
               SUM(b.chain = 'cinepolis')                                 shows_cinepolis,
               COUNT(DISTINCT CASE WHEN b.chain = 'cinemex'   THEN cinema_id END) cinemas_cinemex,
               COUNT(DISTINCT CASE WHEN b.chain = 'cinepolis' THEN cinema_id END) cinemas_cinepolis,
               ROUND(1.0 * SUM(b.chain = 'cinemex')   / (SELECT n FROM n_cin WHERE chain = 'cinemex'), 2)   per_cinema_cinemex,
               ROUND(1.0 * SUM(b.chain = 'cinepolis') / (SELECT n FROM n_cin WHERE chain = 'cinepolis'), 2) per_cinema_cinepolis,
               ROUND(100.0 * SUM(b.chain = 'cinemex')   / (SELECT shows FROM n_cin WHERE chain = 'cinemex'), 1)   share_cinemex,
               ROUND(100.0 * SUM(b.chain = 'cinepolis') / (SELECT shows FROM n_cin WHERE chain = 'cinepolis'), 1) share_cinepolis,
               ROUND(100.0 * SUM(b.chain = 'cinemex')   / (SELECT shows FROM n_cin WHERE chain = 'cinemex')
                   - 100.0 * SUM(b.chain = 'cinepolis') / (SELECT shows FROM n_cin WHERE chain = 'cinepolis'), 1) gap_pp,
               COUNT(*)                                                   shows_total
        FROM base b
        GROUP BY title_norm ORDER BY shows_total DESC LIMIT ?""", params + [limit])


def mix(conn, d0=None, d1=None, from_now=True, hours=None):
    """Share de formato (premium / gran formato / 3D-4D / tradicional) e idioma por cadena."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    return rows(conn, f"""
        WITH base AS (SELECT chain, {_FORMAT_CASE} fmt, {_LANG_CASE} lang FROM current_showtime WHERE {where}),
             tot AS (SELECT chain, COUNT(*) n FROM base GROUP BY chain)
        SELECT 'format' dimension, b.chain, b.fmt bucket, COUNT(*) shows,
               ROUND(100.0 * COUNT(*) / (SELECT n FROM tot WHERE chain = b.chain), 1) share
        FROM base b GROUP BY b.chain, b.fmt
        UNION ALL
        SELECT 'language', b.chain, b.lang, COUNT(*),
               ROUND(100.0 * COUNT(*) / (SELECT n FROM tot WHERE chain = b.chain), 1)
        FROM base b GROUP BY b.chain, b.lang
        ORDER BY 1, 2, 3""", params)


def concentration(conn, d0=None, d1=None, from_now=True, hours=None):
    """Por cadena: HHI de la parrilla (suma de shares² por título, 0–10,000), peso del Top 3 y
    títulos distintos por complejo."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    return rows(conn, f"""
        WITH base AS (SELECT chain, cinema_id, title_norm FROM current_showtime WHERE {where}),
             tot AS (SELECT chain, COUNT(*) n FROM base GROUP BY chain),
             by_title AS (SELECT b.chain, b.title_norm, 100.0 * COUNT(*) / t.n share
                          FROM base b JOIN tot t ON t.chain = b.chain GROUP BY b.chain, b.title_norm),
             ranked AS (SELECT chain, share, ROW_NUMBER() OVER (PARTITION BY chain ORDER BY share DESC) rk FROM by_title),
             per_cinema AS (SELECT chain, cinema_id, COUNT(DISTINCT title_norm) titles FROM base GROUP BY chain, cinema_id)
        SELECT t.chain,
               ROUND((SELECT SUM(share * share) FROM by_title WHERE chain = t.chain))                     hhi,
               ROUND((SELECT SUM(share) FROM ranked WHERE chain = t.chain AND rk <= 3), 1)              top3_pct,
               (SELECT COUNT(*) FROM by_title WHERE chain = t.chain)                                     titles,
               ROUND((SELECT AVG(titles) FROM per_cinema WHERE chain = t.chain), 1)                     titles_per_cinema
        FROM tot t ORDER BY t.chain""", params)


def recent_events(conn, limit=200, kinds=None, chain=None):
    """Últimos cambios detectados. Por defecto excluye 'availability' (ruido de ocupación) y 'expired'
    (funciones que simplemente terminaron; solo sirven para reconstruir historia)."""
    where, params = [], []
    if kinds:
        where.append(f"kind IN ({','.join('?' for _ in kinds)})")
        params.extend(kinds)
    else:
        where.append("kind NOT IN ('availability', 'expired')")
    if chain:
        where.append("chain = ?")
        params.append(chain)
    params.append(limit)
    return rows(conn, f"""
        SELECT e.detected_at, e.chain, e.kind, e.movie_title,
               COALESCE(c.cinema_name, e.cinema_id) cinema_name, e.date, e.datetime_local, e.show_id
        FROM event e
        LEFT JOIN (SELECT chain, cinema_id, MAX(cinema_name) cinema_name
                   FROM current_showtime GROUP BY chain, cinema_id) c
               ON c.chain = e.chain AND c.cinema_id = e.cinema_id
        WHERE {' AND '.join(where)} ORDER BY e.id DESC LIMIT ?""", params)


def events_by_kind(conn, since_hours=24):
    """Conteo de eventos por cadena y tipo en las últimas N horas (sin 'expired', que no es un cambio)."""
    return rows(conn, """
        SELECT chain, kind, COUNT(*) n
        FROM event WHERE kind <> 'expired' AND detected_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ? || ' hours')
        GROUP BY chain, kind ORDER BY chain, n DESC""", (f"-{int(since_hours)}",))
