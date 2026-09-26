"""Oferta independiente: la Cineteca Nacional (y el cine independiente que se sume con el mismo patrón) frente a nuestra
cartelera, fuera del head-to-head.

La Cineteca se captura en las mismas tablas que las cadenas (`chain="cineteca"`) pero no entra a los shares de
Cinemex frente a Cinépolis: es cine de autor, con un solo precio y pocas funciones. Aquí cada medida es % de la
programación de la propia cadena, y la comparación con nosotros es por franja y por título, siempre en CDMX
(`plaza="cdmx"`), la única plaza con sedes de la Cineteca. Los títulos se emparejan con `title_key`, así "Cars 20
aniversario DOB" es la misma película que "Cars".

La ocupación sale de los planos tras el inicio (`occupancy_sample`); `OCCUPANCY_CONFIRMED` dice si la lectura de sus
planos ya se comprobó contra una función llena. Mientras sea False, nada de aquí afirma cifras de ocupación.
"""
import re

from .db import rows
from .labels import SLOTS, US
from .queries import _SLOT_CASE, _window
from .seats import occupancy_by_title

# Lectura del plano de Vista de la Cineteca (`scraper.sample.cineteca_layout`): `OriginalStatus != 0` no vendible y
# `Status != 0` ocupada. Una sola función leída al 2026-09-26, con poca venta; falta confirmarla con una función llena
# (sold_pct contra lo que muestra la web). Al confirmarla se cambia a True y se anota la fecha en `project.md`.
OCCUPANCY_CONFIRMED = False
OCCUPANCY_DAYS = 7          # ventana de planos: una semana de cine
OCCUPANCY_MIN_SAMPLES = 20  # funciones medidas en esa ventana para pintar la ocupación: menos es anécdota
# Umbrales del hallazgo de Capa 1 (`findings._independent_finding`); ajustar con una o dos semanas de planos.
INDEP_MIN_SOLD_PCT = 60.0   # % vendido tras el inicio de un título solo suyo que ya es demanda que no atendemos
INDEP_MIN_SAMPLES = 5       # funciones de ese título medidas en la ventana
# La Cineteca marca el idioma al final del título ("Mary y Max DOB"); el idioma ya va en `language`.
_LANGUAGE_SUFFIX = re.compile(r"\s+(dob|dub|sub)\s*$", re.IGNORECASE)


def _clean(data):
    for r in data:
        r["title"] = _LANGUAGE_SUFFIX.sub("", r["title"] or "")
    return data


def independent_summary(conn, d0=None, d1=None, from_now=True, hours=None, chain="cineteca"):
    """Por sede: `cinema_id`, `cinema_name`, `shows`, `titles` (títulos distintos), `days` y `share_shows` (% de la
    programación de la cadena en la ventana). Orden: funciones descendentes, luego sede."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, chains=(chain,))
    return rows(conn, f"""
        WITH base AS (SELECT cinema_id, cinema_name, date, title_key(title_norm) title_norm FROM current_showtime WHERE {where}),
             tot AS (SELECT COUNT(*) n FROM base)
        SELECT cinema_id, MAX(cinema_name) cinema_name, COUNT(*) shows, COUNT(DISTINCT title_norm) titles,
               COUNT(DISTINCT date) days, ROUND(100.0 * COUNT(*) / (SELECT n FROM tot), 1) share_shows
        FROM base GROUP BY cinema_id ORDER BY shows DESC, cinema_id""", params)


def independent_titles(conn, d0=None, d1=None, from_now=True, hours=None, chain="cineteca", limit=40):
    """Por título (`title_key`, devuelta como `title_norm`): `title`, `shows`, `cinemas`, `share_shows` (% de la
    programación de la cadena), funciones por idioma (`subtitled`, `spanish` y `other`, sin marca de idioma: lengua
    original), `first_date` y `last_date`. Orden: funciones descendentes, luego título."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, chains=(chain,))
    return _clean(rows(conn, f"""
        WITH base AS (SELECT cinema_id, date, language, movie_title, title_key(title_norm) title_norm
                      FROM current_showtime WHERE {where}),
             tot AS (SELECT COUNT(*) n FROM base)
        SELECT title_norm, MIN(movie_title) title, COUNT(*) shows, COUNT(DISTINCT cinema_id) cinemas,
               ROUND(100.0 * COUNT(*) / (SELECT n FROM tot), 1) share_shows,
               SUM(language = 'subtitled') subtitled, SUM(language = 'spanish') spanish,
               SUM(language NOT IN ('subtitled', 'spanish')) other, MIN(date) first_date, MAX(date) last_date
        FROM base GROUP BY title_norm ORDER BY shows DESC, title_norm LIMIT ?""", params + [limit]))


def independent_slots(conn, d0=None, d1=None, from_now=True, hours=None, chain="cineteca", vs=US, plaza="cdmx"):
    """Share de la programación de cada cadena por franja (`labels.SLOTS`): la independiente frente a `vs` en la misma
    plaza. Por fila: `slot`, `chain`, `shows` y `share` (% de las funciones de esa cadena en la ventana); todas las
    franjas de cada cadena con funciones, aun en cero. Orden: `vs` primero, luego la franja en el orden del día."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, plaza=plaza, chains=(vs, chain))
    counts = {(r["chain"], r["slot"]): r["shows"] for r in rows(conn, f"""
        SELECT chain, {_SLOT_CASE} slot, COUNT(*) shows FROM current_showtime WHERE {where}
        GROUP BY chain, slot ORDER BY chain, slot""", params)}
    out = []
    for c in (vs, chain):
        total = sum(v for (ch, _), v in counts.items() if ch == c)
        if not total:
            continue
        for key, _, _, _ in SLOTS:
            shows = counts.get((c, key), 0)
            out.append({"slot": key, "chain": c, "shows": shows, "share": round(100.0 * shows / total, 1)})
    return out


def independent_overlap(conn, d0=None, d1=None, from_now=True, hours=None, chain="cineteca", vs=US, plaza="cdmx"):
    """Cada título de la cadena independiente frente a la cartelera de `vs` en la plaza, por `title_key` (devuelta como
    `title_norm`): `title`, `shows_indep`, `share_indep` (% de su programación), `shows_vs`, `cinemas_vs`, `status`
    (`shared` si `vs` también lo exhibe, `indep_only` si no) y la ocupación tras el inicio de sus funciones en la última
    semana: `samples` y `sold_pct` (None sin planos). Orden: funciones independientes descendentes, luego título."""
    ind_where, ind_params, _ = _window(d0, d1, from_now, hours=hours, chains=(chain,))
    vs_where, vs_params, _ = _window(d0, d1, from_now, hours=hours, plaza=plaza, chains=(vs,))
    data = rows(conn, f"""
        WITH ind AS (SELECT title_key(title_norm) title_norm, MIN(movie_title) title, COUNT(*) shows
                     FROM current_showtime WHERE {ind_where} GROUP BY 1),
             tot AS (SELECT SUM(shows) n FROM ind),
             vs AS (SELECT title_key(title_norm) title_norm, COUNT(*) shows, COUNT(DISTINCT cinema_id) cinemas
                    FROM current_showtime WHERE {vs_where} GROUP BY 1)
        SELECT i.title_norm, i.title, i.shows shows_indep, ROUND(100.0 * i.shows / (SELECT n FROM tot), 1) share_indep,
               COALESCE(v.shows, 0) shows_vs, COALESCE(v.cinemas, 0) cinemas_vs,
               CASE WHEN v.shows THEN 'shared' ELSE 'indep_only' END status
        FROM ind i LEFT JOIN vs v ON v.title_norm = i.title_norm
        ORDER BY i.shows DESC, i.title_norm""", ind_params + vs_params)
    occupancy = {o["title_norm"]: o for o in occupancy_by_title(conn, days=OCCUPANCY_DAYS, chain=chain, min_samples=1)}
    for r in data:
        o = occupancy.get(r["title_norm"])
        r["samples"], r["sold_pct"] = (o["samples"], o["sold_pct"]) if o else (0, None)
    return _clean(data)
