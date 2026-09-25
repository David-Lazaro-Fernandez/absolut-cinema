"""Los conjuntos de datos del explorador (`views/datos.py`) sobre `snapshots.db`. Cada función devuelve renglones planos,
con precios en pesos (las tablas guardan centavos) y con el nombre del cine ya unido, para que la vista solo relabele
y pinte. `DATASETS` declara qué filtros admite cada uno; la vista arma los controles a partir de él.

La búsqueda de texto no distingue mayúsculas ni acentos: compara `norm_title` de ambos lados (función de SQL que
registra `analytics.connect()`). Cada consulta devuelve como mucho `MAX_ROWS` renglones.
"""
from scraper.normalize import norm_title

from .db import rows

MAX_ROWS = 5000

_CATEGORY_TABLES = {"concession_prices": "concession_price", "delivery_prices": "delivery_price"}


def where(clauses, prefix="WHERE"):
    """`clauses`: lista de (condición con `?`, valor). Se omiten las de valor None, vacío o lista vacía. Una lista se
    expande en la condición, que la marca con `{marks}` (`"s.cinema_id IN ({marks})"`). Devuelve (fragmento SQL,
    parámetros); el fragmento es "" si no queda nada."""
    parts, params = [], []
    for cond, value in clauses:
        if value is None or value == "" or (isinstance(value, (list, tuple, set)) and not value):
            continue
        if isinstance(value, (list, tuple, set)):
            parts.append(cond.format(marks=",".join("?" for _ in value)))
            params.extend(value)
        else:
            parts.append(cond)
            params.append(value)
    if not parts:
        return "", []
    return f" {prefix} " + " AND ".join(parts), params


def contains(term):
    """Patrón LIKE para "contiene" sobre texto normalizado, o None si viene vacío."""
    term = norm_title(term or "")
    return f"%{term}%" if term else None


def cinemas(conn, chain=None, search=None, limit=MAX_ROWS):
    """Un renglón por complejo con sus salas y butacas medidas."""
    w, p = where([("c.chain = ?", chain), ("norm_title(c.name) LIKE ?", contains(search))])
    return rows(conn, f"""
        SELECT c.chain, c.cinema_id, c.name AS cinema_name, c.city_id, c.lat, c.lng,
               count(a.screen) AS screens, sum(a.seats) AS seats, min(a.seats) AS min_seats, max(a.seats) AS max_seats,
               max(a.sampled_at) AS sampled_at, c.first_seen, c.last_seen
        FROM cinema c LEFT JOIN auditorium a ON a.chain = c.chain AND a.cinema_id = c.cinema_id
        {w}
        GROUP BY c.chain, c.cinema_id
        ORDER BY c.chain, c.name LIMIT ?""", [*p, limit])


def auditoriums(conn, chain=None, cinema_ids=None, search=None, limit=MAX_ROWS):
    """Un renglón por sala con su última medición de aforo (la tabla guarda solo la más reciente)."""
    w, p = where([("a.chain = ?", chain), ("a.cinema_id IN ({marks})", cinema_ids), ("norm_title(c.name) LIKE ?", contains(search))])
    return rows(conn, f"""
        SELECT a.chain, c.name AS cinema_name, a.screen, a.seats, a.broken, a.sampled_at
        FROM auditorium a JOIN cinema c ON c.chain = a.chain AND c.cinema_id = a.cinema_id
        {w}
        ORDER BY a.chain, c.name, length(a.screen), a.screen LIMIT ?""", [*p, limit])


def week_showtimes(conn, d0, d1, chain=None, cinema_ids=None, search=None, only_open=False, limit=MAX_ROWS):
    """Funciones con fecha entre `d0` y `d1`: las publicadas hoy (`current_showtime`) y, salvo `only_open`, las que ya
    se cerraron en ese rango (canceladas o concluidas), con su última versión tomada del evento de cierre."""
    def filters(alias):
        return where([(f"{alias}chain = ?", chain), (f"{alias}cinema_id IN ({{marks}})", cinema_ids),
                      (f"norm_title({alias}movie_title) LIKE ?", contains(search))], prefix="AND")

    w, p = filters("")
    we, pe = filters("e.")
    closed = "" if only_open else f"""
        UNION ALL
        SELECT e.chain, e.date, json_extract(e.before_json, '$.datetime_local'), e.cinema_id, e.movie_title,
               json_extract(e.before_json, '$.screen'), json_extract(e.before_json, '$.language'),
               json_extract(e.before_json, '$.format'), json_extract(e.before_json, '$.experience'),
               json_extract(e.before_json, '$.premium_tier'), json_extract(e.before_json, '$.availability'),
               json_extract(e.before_json, '$.first_seen'), e.detected_at, e.kind, e.show_id
        FROM event e WHERE e.kind IN ('removed', 'expired') AND e.date BETWEEN ? AND ?
          {we}"""
    return rows(conn, f"""
        WITH s AS (
          SELECT chain, date AS show_date, datetime_local AS starts_at, cinema_id, movie_title, screen, language, format,
                 experience, premium_tier, availability, first_seen AS first_seen_at, NULL AS closed_at, NULL AS closed_kind, show_id
          FROM current_showtime WHERE date BETWEEN ? AND ? {w}{closed})
        SELECT s.chain, s.show_date, s.starts_at, c.name AS cinema_name, s.movie_title, s.screen, s.language, s.format,
               s.experience, s.premium_tier, s.availability, s.first_seen_at, s.closed_at, s.closed_kind, s.show_id
        FROM s JOIN cinema c ON c.chain = s.chain AND c.cinema_id = s.cinema_id
        ORDER BY s.chain, s.show_date, s.starts_at, c.name, s.screen LIMIT ?""",
                [d0, d1, *p, *([] if only_open else [d0, d1, *pe]), limit])


def ticket_prices(conn, d0, d1, chain=None, cinema_ids=None, format_bucket=None, day_type=None, limit=MAX_ROWS):
    """Boleto general y rango por cine, formato y tipo de día, para funciones entre `d0` y `d1`."""
    w, p = where([("ps.chain = ?", chain), ("ps.cinema_id IN ({marks})", cinema_ids),
                  ("ps.format_bucket = ?", format_bucket), ("ps.day_type = ?", day_type)], prefix="AND")
    return rows(conn, f"""
        SELECT ps.chain, c.name AS cinema_name, ps.format_bucket, ps.day_type, ps.date AS show_date,
               ps.datetime_local AS starts_at, ps.general_cents / 100.0 AS general_price, ps.min_cents / 100.0 AS min_price,
               ps.max_cents / 100.0 AS max_price, ps.fee_cents / 100.0 AS fee_price, ps.screen, ps.sampled_at
        FROM price_sample ps JOIN cinema c ON c.chain = ps.chain AND c.cinema_id = ps.cinema_id
        WHERE ps.date BETWEEN ? AND ? {w}
        ORDER BY ps.chain, c.name, ps.format_bucket, ps.day_type, ps.sampled_at DESC LIMIT ?""", [d0, d1, *p, limit])


def _latest(table, keys):
    """La lectura más reciente de cada `keys` en `table` (la primera por `sampled_at` descendente en cada grupo)."""
    return (f"(SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY {keys} ORDER BY sampled_at DESC, id DESC) AS rk "
            f"FROM {table}) WHERE rk = 1)")


def concession_prices(conn, chain=None, cinema_ids=None, category=None, search=None, latest_only=True, limit=MAX_ROWS):
    """Menú de dulcería en sala por complejo. Con `latest_only`, la lectura más reciente de cada producto por cine."""
    w, p = where([("cp.chain = ?", chain), ("cp.cinema_id IN ({marks})", cinema_ids),
                  ("cp.category = ?", category), ("norm_title(cp.product_name) LIKE ?", contains(search))])
    source = _latest("concession_price", "chain, cinema_id, product_id") if latest_only else "concession_price"
    return rows(conn, f"""
        SELECT cp.chain, c.name AS cinema_name, cp.category, cp.sub_category, cp.product_name,
               cp.price_cents / 100.0 AS price, cp.product_structure, cp.promotion_type, cp.active, cp.sampled_at
        FROM {source} cp JOIN cinema c ON c.chain = cp.chain AND c.cinema_id = cp.cinema_id
        {w}
        ORDER BY cp.chain, c.name, cp.category, cp.product_name, cp.sampled_at DESC LIMIT ?""", [*p, limit])


def delivery_prices(conn, platform=None, chain=None, category=None, search=None, latest_only=True, limit=MAX_ROWS):
    """Dulcería a domicilio (Rappi, DiDi Food) por tienda. Con `latest_only`, la última lectura de cada producto."""
    w, p = where([("dp.platform = ?", platform), ("dp.chain = ?", chain), ("dp.category = ?", category),
                  ("norm_title(dp.product_name) LIKE ?", contains(search))])
    source = _latest("delivery_price", "platform, chain, store_id, product_id") if latest_only else "delivery_price"
    return rows(conn, f"""
        SELECT dp.platform, dp.chain, dp.store_name, dp.address, dp.status, dp.category, dp.product_name,
               dp.price_cents / 100.0 AS price, dp.in_stock, dp.description, dp.sampled_at
        FROM {source} dp
        {w}
        ORDER BY dp.platform, dp.chain, dp.store_name, dp.category, dp.product_name LIMIT ?""", [*p, limit])


def cinema_options(conn, chain=None):
    """[{chain, cinema_id, cinema_name}] para el filtro de cines, ordenados por cadena y nombre."""
    w, p = where([("chain = ?", chain)])
    return rows(conn, f"SELECT chain, cinema_id, name AS cinema_name FROM cinema {w} ORDER BY chain, name", p)


def categories(conn, dataset):
    """Categorías distintas de la tabla de precios de un conjunto, ordenadas: [{category}]."""
    table = _CATEGORY_TABLES[dataset]
    return rows(conn, f"SELECT DISTINCT category FROM {table} WHERE category IS NOT NULL ORDER BY 1")


# Qué controles pinta la vista para cada conjunto. Las claves de `filters` son los nombres de los argumentos.
DATASETS = {
    "cinemas": {"fn": cinemas, "filters": ("chain", "search")},
    "auditoriums": {"fn": auditoriums, "filters": ("chain", "cinema_ids", "search")},
    "week_showtimes": {"fn": week_showtimes, "filters": ("dates", "chain", "cinema_ids", "search", "only_open")},
    "ticket_prices": {"fn": ticket_prices, "filters": ("dates", "chain", "cinema_ids", "format_bucket", "day_type")},
    "concession_prices": {"fn": concession_prices, "filters": ("chain", "cinema_ids", "category", "search", "latest_only")},
    "delivery_prices": {"fn": delivery_prices, "filters": ("platform", "chain", "category", "search", "latest_only")},
}
