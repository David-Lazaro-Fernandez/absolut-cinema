"""Dulcería: menú y precios por complejo (hoy solo Cinépolis; Cinemex llegará del cliente).

Cada cine se muestrea completo cada 7 días en `concession_price`; aquí siempre se usa la última muestra de cada
cine. Un producto puede aparecer en varias categorías ("Para ti", "Promociones" repiten productos): se
deduplica por (cine, product_id) quedándose con la categoría no promocional.
"""
from .db import rows
from .plaza import plaza_cinema_where

# Canasta comparable entre complejos: nombres exactos del menú de Cinépolis (categorías Clásicos y Combos).
# Palomitas y Refresco son "compound": el precio es el del tamaño base; los tamaños van como modificadores.
BASKET = ["Palomitas", "Refresco", "Nachos", "Hot Dog Individual", "ICEE®", "Agua Embotellada",
          "Combo Clásico", "Combo Nachos", "Combo Junior", "Maxicombo Nachos"]

_LATEST = """
    latest AS (SELECT chain, cinema_id, MAX(sampled_at) sampled_at FROM concession_price WHERE 1 = 1{scope} GROUP BY chain, cinema_id),
    menu AS (SELECT c.*, ROW_NUMBER() OVER (PARTITION BY c.chain, c.cinema_id, c.product_id
                                            ORDER BY c.category IN ('Para ti', 'Promociones', 'Promocionales'), c.id) rk
             FROM concession_price c JOIN latest l USING (chain, cinema_id, sampled_at)
             WHERE c.price_cents IS NOT NULL AND c.price_cents > 0),
    m AS (SELECT * FROM menu WHERE rk = 1),
    names AS (SELECT chain, cinema_id, name cinema_name FROM cinema)
"""


def _latest(plaza):
    """CTEs de la última muestra por cine, acotadas a la plaza; devuelve (sql, params) para anteponer a los demás."""
    scope, params = plaza_cinema_where(plaza)
    return _LATEST.format(scope=scope), params


def concession_summary(conn, chain="cinepolis", plaza=None):
    """Cines muestreados, productos distintos, precio mediano del menú y fecha de la última muestra."""
    latest, scope = _latest(plaza)
    return rows(conn, f"""
        WITH {latest},
        ranked AS (SELECT price_cents, ROW_NUMBER() OVER (ORDER BY price_cents) rk, COUNT(*) OVER () n FROM m WHERE chain = ?)
        SELECT (SELECT COUNT(DISTINCT cinema_id) FROM m WHERE chain = ?) cinemas,
               (SELECT COUNT(DISTINCT product_id) FROM m WHERE chain = ?) products,
               (SELECT COUNT(*) FROM m WHERE chain = ?) listings,
               (SELECT MAX(sampled_at) FROM latest WHERE chain = ?) last_sampled,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN price_cents END) / 100.0, 0) median_price
        FROM ranked""", (*scope, chain, chain, chain, chain, chain))


def concession_basket(conn, chain="cinepolis", plaza=None):
    """Por producto de la canasta: cines que lo venden, mediana, mínimo, máximo y dispersión (máx/mín − 1)."""
    marks = ",".join("?" * len(BASKET))
    latest, scope = _latest(plaza)
    out = rows(conn, f"""
        WITH {latest},
        b AS (SELECT product_name, cinema_id, price_cents,
                     ROW_NUMBER() OVER (PARTITION BY product_name ORDER BY price_cents) rk, COUNT(*) OVER (PARTITION BY product_name) n
              FROM m WHERE chain = ? AND product_name IN ({marks}))
        SELECT product_name, COUNT(DISTINCT cinema_id) cinemas,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN price_cents END) / 100.0, 0) median_price,
               MIN(price_cents) / 100.0 min_price, MAX(price_cents) / 100.0 max_price,
               ROUND(100.0 * (MAX(price_cents) - MIN(price_cents)) / MIN(price_cents), 0) spread_pct,
               COUNT(DISTINCT price_cents) distinct_prices
        FROM b GROUP BY product_name""", (*scope, chain, *BASKET))
    order = {name: i for i, name in enumerate(BASKET)}
    return sorted(out, key=lambda r: order.get(r["product_name"], 99))


def concession_product_by_cinema(conn, product_name, chain="cinepolis", plaza=None):
    """Precio de un producto en cada complejo, de mayor a menor, con `cinema_type` (vip | traditional)."""
    latest, scope = _latest(plaza)
    return rows(conn, f"""
        WITH {latest}
        SELECT m.cinema_id, COALESCE(n.cinema_name, m.cinema_id) cinema_name, m.price_cents / 100.0 price, m.category,
               CASE WHEN m.cinema_id LIKE '%vip%' THEN 'vip' ELSE 'traditional' END cinema_type
        FROM m LEFT JOIN names n ON n.chain = m.chain AND n.cinema_id = m.cinema_id
        WHERE m.chain = ? AND m.product_name = ? ORDER BY price DESC, cinema_name""", (*scope, chain, product_name))


def concession_by_cinema(conn, chain="cinepolis", plaza=None):
    """Por complejo: productos, categorías, precio mediano del menú y la canasta pivotada (una columna por producto)."""
    latest, scope = _latest(plaza)
    base = rows(conn, f"""
        WITH {latest},
        ranked AS (SELECT cinema_id, price_cents, ROW_NUMBER() OVER (PARTITION BY cinema_id ORDER BY price_cents) rk,
                          COUNT(*) OVER (PARTITION BY cinema_id) n FROM m WHERE chain = ?)
        SELECT r.cinema_id, COALESCE(n.cinema_name, r.cinema_id) cinema_name, MAX(r.n) products,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN price_cents END) / 100.0, 0) median_price,
               (SELECT COUNT(DISTINCT category) FROM m WHERE m.chain = ? AND m.cinema_id = r.cinema_id) categories
        FROM ranked r LEFT JOIN names n ON n.chain = ? AND n.cinema_id = r.cinema_id
        GROUP BY r.cinema_id ORDER BY median_price DESC""", (*scope, chain, chain, chain))
    marks = ",".join("?" * len(BASKET))
    prices = rows(conn, f"""
        WITH {latest}
        SELECT cinema_id, product_name, price_cents / 100.0 price FROM m WHERE chain = ? AND product_name IN ({marks})""",
        (*scope, chain, *BASKET))
    by = {}
    for r in prices:
        by.setdefault(r["cinema_id"], {})[r["product_name"]] = r["price"]
    for r in base:
        for name in BASKET:
            r[name] = by.get(r["cinema_id"], {}).get(name)
    return base


def concession_categories(conn, chain="cinepolis", plaza=None):
    """Categorías del menú: en cuántos cines aparecen y cuántos productos distintos suman."""
    latest, scope = _latest(plaza)
    return rows(conn, f"""
        WITH {latest}
        SELECT category, COUNT(DISTINCT cinema_id) cinemas, COUNT(DISTINCT product_id) products,
               ROUND(AVG(price_cents) / 100.0, 0) avg_price
        FROM m WHERE chain = ? AND category <> '' GROUP BY category ORDER BY cinemas DESC, products DESC""", (*scope, chain))
