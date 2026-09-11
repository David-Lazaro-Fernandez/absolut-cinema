"""Los conjuntos de datos del explorador (`views/datos.py`). Cada función devuelve renglones planos, con precios en
pesos (las tablas guardan centavos) y con el nombre del cine ya unido, para que la vista solo relabele y pinte.
`DATASETS` declara qué filtros admite cada uno; la vista arma los controles a partir de él."""
from .db import rows
from .sql import like, where

MAX_ROWS = 5000

# Última medición de cada sala: el aforo se vuelve a medir cada mes y solo cuenta la lectura más reciente.
_LATEST_AUDITORIUM = """
    SELECT DISTINCT ON (chain, cinema_id, screen) chain, cinema_id, screen, seats, broken, sampled_at
    FROM auditorium ORDER BY chain, cinema_id, screen, sampled_at DESC"""


def cinemas(conn, chain=None, search=None, limit=MAX_ROWS):
    """Un renglón por complejo con sus salas y butacas medidas."""
    w, p = where([("c.chain = %s::chain_t", chain), ("c.name ILIKE %s", like(search))])
    return rows(conn, f"""
        SELECT c.chain::text AS chain, c.cinema_id, c.name AS cinema_name, c.city_id, c.lat, c.lng,
               count(a.screen) AS screens, sum(a.seats) AS seats, min(a.seats) AS min_seats, max(a.seats) AS max_seats,
               max(a.sampled_at) AS sampled_at, c.first_seen, c.last_seen
        FROM cinema c LEFT JOIN ({_LATEST_AUDITORIUM}) a USING (chain, cinema_id)
        {w}
        GROUP BY c.chain, c.cinema_id, c.name, c.city_id, c.lat, c.lng, c.first_seen, c.last_seen
        ORDER BY c.chain, c.name LIMIT %s""", [*p, limit])


def auditoriums(conn, chain=None, cinema_ids=None, search=None, limit=MAX_ROWS):
    """Un renglón por sala con su última medición de aforo."""
    w, p = where([("a.chain = %s::chain_t", chain), ("a.cinema_id = ANY(%s)", cinema_ids), ("c.name ILIKE %s", like(search))])
    return rows(conn, f"""
        SELECT a.chain::text AS chain, c.name AS cinema_name, a.screen, a.seats, a.broken, a.sampled_at
        FROM ({_LATEST_AUDITORIUM}) a JOIN cinema c USING (chain, cinema_id)
        {w}
        ORDER BY a.chain, c.name, length(a.screen), a.screen LIMIT %s""", [*p, limit])


def week_showtimes(conn, d0, d1, chain=None, cinema_ids=None, search=None, only_open=False, limit=MAX_ROWS):
    """Funciones publicadas entre `d0` y `d1` con su estado vigente (última versión). `only_open` excluye las que ya
    se cerraron (canceladas o concluidas). El rango de fechas es obligatorio: poda las particiones mensuales."""
    w, p = where([("s.chain = %s::chain_t", chain), ("s.cinema_id = ANY(%s)", cinema_ids),
                  ("m.title ILIKE %s", like(search))], prefix="AND")
    if only_open:
        w += " AND s.closed_at IS NULL"
    return rows(conn, f"""
        SELECT s.chain::text AS chain, s.show_date, st.starts_at, c.name AS cinema_name, m.title AS movie_title,
               st.screen, st.language, st.format, st.experience, st.premium_tier, st.availability,
               s.first_seen_at, s.closed_at, s.closed_kind, s.show_id
        FROM showtime s
        JOIN showtime_state st ON st.chain = s.chain AND st.show_id = s.show_id AND st.show_date = s.show_date
                              AND st.valid_to IS NULL
        JOIN cinema c ON c.chain = s.chain AND c.cinema_id = s.cinema_id
        JOIN movie m ON m.chain = s.chain AND m.movie_id = s.movie_id
        WHERE s.show_date BETWEEN %s AND %s {w}
        ORDER BY s.chain, s.show_date, st.starts_at, c.name, st.screen LIMIT %s""", [d0, d1, *p, limit])


def ticket_prices(conn, d0, d1, chain=None, cinema_ids=None, format_bucket=None, day_type=None, limit=MAX_ROWS):
    """Boleto general y rango por cine, formato y tipo de día, para funciones entre `d0` y `d1`."""
    w, p = where([("ps.chain = %s::chain_t", chain), ("ps.cinema_id = ANY(%s)", cinema_ids),
                  ("ps.format_bucket = %s", format_bucket), ("ps.day_type = %s", day_type)], prefix="AND")
    return rows(conn, f"""
        SELECT ps.chain::text AS chain, c.name AS cinema_name, ps.format_bucket, ps.day_type, ps.show_date, ps.starts_at,
               ps.general_cents / 100.0 AS general_price, ps.min_cents / 100.0 AS min_price, ps.max_cents / 100.0 AS max_price,
               ps.fee_cents / 100.0 AS fee_price, ps.screen, ps.sampled_at
        FROM price_sample ps JOIN cinema c ON c.chain = ps.chain AND c.cinema_id = ps.cinema_id
        WHERE ps.show_date BETWEEN %s AND %s {w}
        ORDER BY ps.chain, c.name, ps.format_bucket, ps.day_type, ps.sampled_at DESC LIMIT %s""", [d0, d1, *p, limit])


def concession_prices(conn, chain=None, cinema_ids=None, category=None, search=None, latest_only=True, limit=MAX_ROWS):
    """Menú de dulcería en sala por complejo. Con `latest_only`, la lectura más reciente de cada producto por cine."""
    w, p = where([("cp.chain = %s::chain_t", chain), ("cp.cinema_id = ANY(%s)", cinema_ids),
                  ("cp.category = %s", category), ("cp.product_name ILIKE %s", like(search))])
    source = ("(SELECT DISTINCT ON (chain, cinema_id, product_id) * FROM concession_price "
              "ORDER BY chain, cinema_id, product_id, sampled_at DESC)" if latest_only else "concession_price")
    return rows(conn, f"""
        SELECT cp.chain::text AS chain, c.name AS cinema_name, cp.category, cp.sub_category, cp.product_name,
               cp.price_cents / 100.0 AS price, cp.product_structure, cp.promotion_type, cp.active, cp.sampled_at
        FROM {source} cp JOIN cinema c ON c.chain = cp.chain AND c.cinema_id = cp.cinema_id
        {w}
        ORDER BY cp.chain, c.name, cp.category, cp.product_name, cp.sampled_at DESC LIMIT %s""", [*p, limit])


def delivery_prices(conn, platform=None, chain=None, category=None, search=None, latest_only=True, limit=MAX_ROWS):
    """Dulcería a domicilio (Rappi, DiDi Food) por tienda. Con `latest_only`, la última lectura de cada producto."""
    w, p = where([("dp.platform = %s", platform), ("dp.chain = %s::chain_t", chain), ("dp.category = %s", category),
                  ("dp.product_name ILIKE %s", like(search))])
    source = ("(SELECT DISTINCT ON (platform, chain, store_id, product_id) * FROM delivery_price "
              "ORDER BY platform, chain, store_id, product_id, sampled_at DESC)" if latest_only else "delivery_price")
    return rows(conn, f"""
        SELECT dp.platform, dp.chain::text AS chain, dp.store_name, dp.address, dp.status, dp.category, dp.product_name,
               dp.price_cents / 100.0 AS price, dp.in_stock, dp.description, dp.sampled_at
        FROM {source} dp
        {w}
        ORDER BY dp.platform, dp.chain, dp.store_name, dp.category, dp.product_name LIMIT %s""", [*p, limit])


# Qué controles pinta la vista para cada conjunto. Las claves de `filters` son los nombres de los argumentos.
DATASETS = {
    "cinemas": {"fn": cinemas, "filters": ("chain", "search")},
    "auditoriums": {"fn": auditoriums, "filters": ("chain", "cinema_ids", "search")},
    "week_showtimes": {"fn": week_showtimes, "filters": ("dates", "chain", "cinema_ids", "search", "only_open")},
    "ticket_prices": {"fn": ticket_prices, "filters": ("dates", "chain", "cinema_ids", "format_bucket", "day_type")},
    "concession_prices": {"fn": concession_prices, "filters": ("chain", "cinema_ids", "category", "search", "latest_only")},
    "delivery_prices": {"fn": delivery_prices, "filters": ("platform", "chain", "category", "search", "latest_only")},
}
