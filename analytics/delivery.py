"""Dulcería a domicilio: precios de Cinemex y Cinépolis en Rappi y DiDi Food (tabla `delivery_price`).

Siempre se usa la última lectura de cada tienda. Los nombres de producto difieren entre cadenas ("Combo
Tradicional" vs "Palomitas Cinépolis & Refresco"), así que la comparación entre cadenas va por **cubetas**
(`DELIVERY_BUCKETS`, expresiones sobre el nombre), no por nombre exacto. Es catálogo "para llevar", no tablero de sala.
"""
import re
import statistics

from .db import rows

# (cubeta, etiqueta, patrón sobre el nombre en minúsculas). El primer patrón que coincide gana.
DELIVERY_BUCKETS = [
    ("combo_hotdog", "Combo con hot dog", r"combo.*hot ?dog"),
    ("combo_nachos", "Combo con nachos", r"combo.*nacho"),
    ("combo_basico", "Combo palomitas + refresco", r"(combo (tradicional|individual|pareja|palomitas|cl[aá]sico))|(palomitas.*&.*refresco)"),
    ("palomitas", "Palomitas solas", r"^(mega )?palomitas"),
    ("hotdog", "Hot dog solo", r"^hot ?dog"),
    ("nachos", "Nachos solos", r"^nachos"),
    ("refresco", "Refresco / bebida", r"coca|sprite|fanta|sidral|refresco|fuze|del valle|agua "),
    ("dulces", "Dulces", r"m&m|skittles|skwinkles|lifesavers|gomita|ositos|aritos|snickers|kitkat|milky"),
    ("helado", "Helado", r"magnum|cornetto|micha|helado"),
]

_LATEST = """
    latest AS (SELECT platform, store_id, MAX(sampled_at) sampled_at FROM delivery_price GROUP BY platform, store_id),
    m AS (SELECT d.* FROM delivery_price d JOIN latest l USING (platform, store_id, sampled_at)
          WHERE d.price_cents IS NOT NULL AND d.price_cents > 0)
"""


def bucket_of(name):
    n = (name or "").lower()
    for key, label, pat in DELIVERY_BUCKETS:
        if re.search(pat, n):
            return key
    return None


def delivery_summary(conn):
    """Por plataforma y cadena: tiendas, productos distintos, referencias, % de productos con un solo precio en
    todas las tiendas (precio nacional) y fecha de la última lectura."""
    base = rows(conn, f"""
        WITH {_LATEST},
        per_prod AS (SELECT platform, chain, product_name, COUNT(DISTINCT price_cents) n_prices, COUNT(DISTINCT store_id) n_stores
                     FROM m GROUP BY platform, chain, product_name)
        SELECT m.platform, m.chain, COUNT(DISTINCT m.store_id) stores, COUNT(DISTINCT m.product_name) products, COUNT(*) listings,
               MAX(m.sampled_at) last_sampled,
               (SELECT ROUND(100.0 * SUM(n_prices = 1) / COUNT(*), 0) FROM per_prod p
                 WHERE p.platform = m.platform AND p.chain = m.chain AND p.n_stores >= 3) pct_single_price
        FROM m GROUP BY m.platform, m.chain ORDER BY m.platform, m.chain""")
    return base


def delivery_products(conn, chain="cinemex", platform=None):
    """Por producto (última lectura por tienda): tiendas que lo venden, mediana, mínimo, máximo, precios distintos."""
    where = "AND platform = ?" if platform else ""
    params = (chain, platform) if platform else (chain,)
    return rows(conn, f"""
        WITH {_LATEST},
        b AS (SELECT product_name, MIN(category) category, platform || ':' || store_id st, price_cents, MIN(description) description
              FROM m WHERE chain = ? {where} GROUP BY product_name, platform, store_id, price_cents),
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY product_name ORDER BY price_cents) rk, COUNT(*) OVER (PARTITION BY product_name) n FROM b)
        SELECT product_name, MIN(category) category, COUNT(DISTINCT st) stores,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN price_cents END) / 100.0, 0) median_price,
               MIN(price_cents) / 100.0 min_price, MAX(price_cents) / 100.0 max_price, COUNT(DISTINCT price_cents) distinct_prices,
               MIN(description) description
        FROM r GROUP BY product_name ORDER BY stores DESC, median_price DESC""", params)


def delivery_compare(conn, platform=None):
    """Cinemex vs Cinépolis por cubeta comparable: mediana del precio (sobre la última lectura de cada tienda),
    número de tiendas y el producto más común de cada cadena en la cubeta."""
    where = "AND platform = ?" if platform else ""
    data = rows(conn, f"""
        WITH {_LATEST}
        SELECT chain, platform, store_id, product_name, price_cents FROM m WHERE 1 = 1 {where}""", (platform,) if platform else ())
    agg = {}
    for r in data:
        b = bucket_of(r["product_name"])
        if not b:
            continue
        a = agg.setdefault((b, r["chain"]), {"prices": [], "stores": set(), "names": {}})
        a["prices"].append(r["price_cents"]); a["stores"].add((r["platform"], r["store_id"]))
        a["names"][r["product_name"]] = a["names"].get(r["product_name"], 0) + 1
    out = []
    for key, label, _ in DELIVERY_BUCKETS:
        row = {"bucket": key, "label": label}
        any_ = False
        for chain in ("cinemex", "cinepolis"):
            a = agg.get((key, chain))
            if a:
                any_ = True
                row[f"{chain}_median"] = round(statistics.median(a["prices"]) / 100.0, 0)
                row[f"{chain}_min"] = min(a["prices"]) / 100.0
                row[f"{chain}_max"] = max(a["prices"]) / 100.0
                row[f"{chain}_stores"] = len(a["stores"])
                row[f"{chain}_product"] = max(a["names"], key=a["names"].get)
            else:
                row.update({f"{chain}_median": None, f"{chain}_min": None, f"{chain}_max": None, f"{chain}_stores": 0, f"{chain}_product": None})
        if any_:
            a, c = row["cinemex_median"], row["cinepolis_median"]
            row["delta_pct"] = round(100.0 * (c - a) / a, 0) if a and c else None
            out.append(row)
    return out


def delivery_stores(conn, chain="cinemex", platform=None):
    """Tiendas: plataforma, nombre, dirección, estado, productos y precio mediano, con su última lectura."""
    where = "AND platform = ?" if platform else ""
    params = (chain, platform) if platform else (chain,)
    return rows(conn, f"""
        WITH {_LATEST},
        r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY platform, store_id ORDER BY price_cents) rk,
                     COUNT(*) OVER (PARTITION BY platform, store_id) n FROM m WHERE chain = ? {where})
        SELECT platform, store_id, MAX(store_name) store_name, MAX(address) address, MAX(status) status, MAX(available) available,
               MAX(lat) lat, MAX(lng) lng, MAX(n) products,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN price_cents END) / 100.0, 0) median_price, MAX(sampled_at) sampled_at
        FROM r GROUP BY platform, store_id ORDER BY platform, store_name""", params)
