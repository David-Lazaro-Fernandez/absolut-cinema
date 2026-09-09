"""Resumen general en el formato que el cliente lee a diario: funciones por película y cadena, con
participación de cada cadena, diferencia en funciones y en puntos, y la razón Cinépolis/Cinemex; Top N,
"Resto" y "Total de programación". Alcance: la plaza capturada (CDMX), semana de cine jueves a miércoles.
"""
from .queries import _window, rows

REST, TOTAL = "__resto__", "__total__"


def general_summary(conn, d0=None, d1=None, from_now=True, hours=None, top=11):
    """Filas ordenadas: las `top` películas con más funciones (ambas cadenas), luego `kind='rest'` y `kind='total'`.
    Por fila: `shows_*`, `cinemas_*`, `share_*` (% de la programación de cada cadena en la ventana),
    `diff_shows` (Cinemex − Cinépolis), `diff_pp` (share Cinemex − share Cinépolis) y `ratio`
    (funciones Cinépolis / funciones Cinemex, None si Cinemex no la exhibe). `hours` recorta por hora de inicio."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    data = rows(conn, f"""
        WITH base AS (SELECT chain, cinema_id, title_norm, movie_title FROM current_showtime WHERE {where}),
             tot AS (SELECT chain, COUNT(*) shows, COUNT(DISTINCT cinema_id) cinemas FROM base GROUP BY chain),
             topn AS (SELECT title_norm FROM base GROUP BY title_norm ORDER BY COUNT(*) DESC, title_norm LIMIT ?),
             grp AS (SELECT CASE WHEN title_norm IN (SELECT title_norm FROM topn) THEN title_norm ELSE '{REST}' END g,
                            chain, cinema_id, movie_title FROM base)
        SELECT g title_norm,
               COALESCE(MAX(CASE WHEN chain = 'cinemex' THEN movie_title END), MAX(movie_title)) title,
               SUM(chain = 'cinemex') shows_cinemex, SUM(chain = 'cinepolis') shows_cinepolis,
               COUNT(DISTINCT CASE WHEN chain = 'cinemex' THEN cinema_id END) cinemas_cinemex,
               COUNT(DISTINCT CASE WHEN chain = 'cinepolis' THEN cinema_id END) cinemas_cinepolis,
               ROUND(100.0 * SUM(chain = 'cinemex') / (SELECT shows FROM tot WHERE chain = 'cinemex'), 1) share_cinemex,
               ROUND(100.0 * SUM(chain = 'cinepolis') / (SELECT shows FROM tot WHERE chain = 'cinepolis'), 1) share_cinepolis
        FROM grp GROUP BY g
        ORDER BY g = '{REST}', shows_cinemex + shows_cinepolis DESC, g""", params + [top])
    totals = {r["chain"]: r for r in rows(conn, f"""
        SELECT chain, COUNT(*) shows, COUNT(DISTINCT cinema_id) cinemas FROM current_showtime WHERE {where} GROUP BY chain""", params)}
    out = []
    for r in data:
        r["kind"] = "rest" if r["title_norm"] == REST else "title"
        out.append(_derive(r))
    cmx, cnp = totals.get("cinemex", {}), totals.get("cinepolis", {})
    out.append(_derive({"title_norm": TOTAL, "title": None, "kind": "total",
                        "shows_cinemex": cmx.get("shows", 0), "shows_cinepolis": cnp.get("shows", 0),
                        "cinemas_cinemex": cmx.get("cinemas", 0), "cinemas_cinepolis": cnp.get("cinemas", 0),
                        "share_cinemex": 100.0 if cmx else None, "share_cinepolis": 100.0 if cnp else None}))
    return out


def _derive(r):
    a, c = r["shows_cinemex"] or 0, r["shows_cinepolis"] or 0
    r["diff_shows"] = a - c
    r["diff_pp"] = round((r["share_cinemex"] or 0) - (r["share_cinepolis"] or 0), 1)
    r["ratio"] = round(c / a, 2) if a else None
    return r
