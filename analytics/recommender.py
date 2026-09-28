"""Recomendador de funciones: las funciones cerca de un punto que caben en el presupuesto de un grupo (adultos, niños y
tercera edad), con boletos y dulcería.

Boletos: la lectura de precio más reciente del cine para el mismo formato y tipo de día, sin eventos ni matinés. Es
precio de lista, no el de esa función. El adulto paga el boleto general. Niños y tercera edad se buscan por nombre del
boleto ("MENOR", "Niños", "3ra Edad"); si la función no los tiene, pagan el general. Una función sin lectura no se
estima: queda sin precio y fuera del presupuesto.

Dulcería: los paquetes de `SNACK_PACKAGES` con el menú en sala de cada cine. Solo Cinépolis publica ese menú. En
Cinemex y la Cineteca el paquete queda sin precio (`snacks_total` None).

La distancia es en línea recta (haversine). En un empate, Cinemex va primero.
"""
import json
import math
import unicodedata

from .cinema_locations import _NOT_EVENT, MAP_CHAINS, display_name
from .concessions import concession_product_by_cinema
from .db import rows
from .labels import CHAIN_LABEL, US
from .plaza import plaza_where
from .queries import _FORMAT_CASE, _window
from .seats import _DAY_TYPE_CASE

SORTS = ("distance", "price", "time")
# "complete": boletos y dulcería con precio. "snacks_unpriced": la dulcería no tiene precio. "unpriced": los boletos
# no tienen precio. Solo "complete" compite por el presupuesto; las otras van aparte para no parecer más baratas.
STATUSES = ("complete", "snacks_unpriced", "unpriced")
# Paquete → [(producto del menú de Cinépolis, cuántas personas cubre cada uno)].
SNACK_PACKAGES = {
    "none": [],
    "popcorn": [("Palomitas", 1), ("Refresco", 1)],        # tamaño base
    "combo": [("Combo Clásico", 2)],
}
_CHILD_WORDS = ("menor", "nino")
_SENIOR_WORDS = ("mayor", "tercera", "3 era", "3ra", "3a edad")
_EARTH_KM = 6371.0
_KM_PER_DEGREE = 111.32


def _distance_km(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * _EARTH_KM * math.asin(math.sqrt(a))


def _plain(text):
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _ticket_prices(tickets_json, general_cents):
    """(adulto, niño, tercera edad) en pesos de una lectura. De varios boletos de niño o de tercera edad toma el más caro
    que no pase del general (el regular, no una promoción); si no hay, el general."""
    general = general_cents / 100.0
    tickets = [t for t in json.loads(tickets_json or "[]") if isinstance(t.get("cents"), int) and t["cents"] > 0]

    def pick(words):
        found = [t["cents"] / 100.0 for t in tickets if any(w in _plain(t.get("name")) for w in words)]
        regular = [c for c in found if c <= general]
        return max(regular or found) if found else general
    return general, pick(_CHILD_WORDS), pick(_SENIOR_WORDS)


def _snack_prices(conn, snacks, people):
    """{(chain, cinema_id): costo del paquete para `people`} de los cines con todos sus productos en el menú."""
    items = SNACK_PACKAGES[snacks]
    if not items:
        return {}
    per_cinema = {}
    for product, covers in items:
        units = math.ceil(people / covers)
        for r in concession_product_by_cinema(conn, product):
            per_cinema.setdefault(r["cinema_id"], {})[product] = r["price"] * units
    return {("cinepolis", cinema_id): round(sum(p.values()), 2) for cinema_id, p in per_cinema.items() if len(p) == len(items)}


def _candidates(conn, lat, lng, *, d0, d1, from_now, hours, radius_km, title_norm, formats, adults, children, seniors, snacks):
    """Todas las funciones de la ventana a `radius_km` o menos, con boletos, dulcería, costo y distancia, sin ordenar."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, chains=MAP_CHAINS)
    dlat = radius_km / _KM_PER_DEGREE
    dlng = radius_km / (_KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    data = rows(conn, f"""
        WITH f AS (SELECT chain, show_id, cinema_id, movie_title, title_key(title_norm) title_norm, date, datetime_local,
                          language, {_FORMAT_CASE} format_bucket, {_DAY_TYPE_CASE} day_type
                   FROM current_showtime WHERE {where}),
             p AS (SELECT chain, cinema_id, format_bucket, day_type, general_cents, tickets_json, sampled_at,
                          ROW_NUMBER() OVER (PARTITION BY chain, cinema_id, format_bucket, day_type
                                             ORDER BY sampled_at DESC, id DESC) rk
                   FROM price_sample WHERE general_cents > 0 AND {_NOT_EVENT})
        SELECT f.chain, f.show_id, f.cinema_id, c.name cinema_name, c.lat, c.lng, f.movie_title title, f.title_norm,
               f.date, f.datetime_local, f.language, f.format_bucket, f.day_type,
               p.general_cents, p.tickets_json, p.sampled_at price_sampled_at
        FROM f JOIN cinema c ON c.chain = f.chain AND c.cinema_id = f.cinema_id
        LEFT JOIN p ON p.rk = 1 AND p.chain = f.chain AND p.cinema_id = f.cinema_id
                   AND p.format_bucket = f.format_bucket AND p.day_type = f.day_type
        WHERE c.lat BETWEEN ? AND ? AND c.lng BETWEEN ? AND ?
        ORDER BY f.chain, f.show_id""", params + [lat - dlat, lat + dlat, lng - dlng, lng + dlng])
    snack_costs = _snack_prices(conn, snacks, adults + children + seniors)
    reference = _snack_prices(conn, "popcorn", 1)
    out = []
    for r in data:
        if title_norm and r["title_norm"] != title_norm or formats and r["format_bucket"] not in formats:
            continue
        r["distance_km"] = round(_distance_km(lat, lng, r["lat"], r["lng"]), 2)
        if r["distance_km"] > radius_km:
            continue
        r["cinema_name"] = display_name(r["cinema_id"], r["cinema_name"])
        general, tickets = r.pop("general_cents"), r.pop("tickets_json")
        if general:
            r["adult_price"], r["child_price"], r["senior_price"] = _ticket_prices(tickets, general)
            r["tickets_total"] = round(adults * r["adult_price"] + children * r["child_price"] + seniors * r["senior_price"], 2)
        else:
            r["adult_price"] = r["child_price"] = r["senior_price"] = r["tickets_total"] = None
        r["snacks_total"] = 0.0 if snacks == "none" else snack_costs.get((r["chain"], r["cinema_id"]))
        r["snack_reference"] = reference.get((r["chain"], r["cinema_id"]))
        r["total"] = round(r["tickets_total"] + r["snacks_total"], 2) \
            if r["tickets_total"] is not None and r["snacks_total"] is not None else None
        r["status"] = "unpriced" if r["tickets_total"] is None else "complete" if r["total"] is not None else "snacks_unpriced"
        out.append(r)
    return out


def _cost(r):
    """Lo que se compara contra el presupuesto y ordena por precio: el total, o los boletos si la dulcería no tiene precio."""
    return r["total"] if r["total"] is not None else r["tickets_total"]


def _sort_key(sort):
    us_first = lambda r: r["chain"] != US  # noqa: E731
    price = lambda r: _cost(r) if _cost(r) is not None else math.inf  # noqa: E731
    keys = {"distance": lambda r: (r["distance_km"], price(r), us_first(r), r["datetime_local"], r["show_id"]),
            "price": lambda r: (price(r), r["distance_km"], us_first(r), r["datetime_local"], r["show_id"]),
            "time": lambda r: (r["datetime_local"], r["distance_km"], price(r), us_first(r), r["show_id"])}
    return keys[sort]


def _fits(r, budget):
    """Una función entra si su costo conocido cabe: el total si está completo, los boletos si falta la dulcería."""
    return r["status"] != "unpriced" and (budget is None or _cost(r) <= budget)


def recommend(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, adults=2, children=0, seniors=0,
              snacks="none", budget=None, radius_km=5.0, title_norm=None, formats=None, status="complete", sort="distance",
              per_cinema=None, limit=40):
    """Funciones a `radius_km` o menos de (`lat`, `lng`) para un grupo de `adults`, `children` y `seniors` con el
    paquete `snacks` (clave de `SNACK_PACKAGES`). Solo devuelve las del `status` pedido (ver `STATUSES`). `budget`
    (None = sin tope) se aplica al `total` en "complete" y a los boletos en "snacks_unpriced". `title_norm` y `formats`
    acotan la búsqueda.
    Por fila: `chain`, `show_id`, `cinema_id`, `cinema_name`, `lat`, `lng`, `title`, `title_norm`, `date`,
    `datetime_local`, `language`, `format_bucket`, `day_type`, `price_sampled_at`, `adult_price`, `child_price`,
    `senior_price`, `tickets_total`, `snacks_total` (0 sin paquete, None sin precio), `snack_reference` (palomitas y
    refresco de una persona; None sin menú), `total` (None sin precio de dulcería), `status` y `distance_km`.
    Orden según `sort` ("distance", "price" o "time"). `per_cinema` limita las funciones de cada cine."""
    found = [r for r in _candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                                    title_norm=title_norm, formats=formats, adults=adults, children=children,
                                    seniors=seniors, snacks=snacks)
             if r["status"] == status and (status == "unpriced" or _fits(r, budget))]
    out, taken = [], {}
    for r in sorted(found, key=_sort_key(sort)):
        k = (r["chain"], r["cinema_id"])
        if per_cinema and taken.get(k, 0) >= per_cinema:
            continue
        taken[k] = taken.get(k, 0) + 1
        out.append(r)
    return out[:limit]


def recommend_summary(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, adults=2, children=0, seniors=0,
                      snacks="none", budget=None, radius_km=5.0, title_norm=None, formats=None):
    """Resumen de lo que `recommend` encuentra, sin límite: `shows` y `cinemas` (funciones de costo completo que caben y
    sus cines), `snacks_unpriced` (funciones cuyos boletos caben pero sin precio del paquete de dulcería), `unpriced`
    (funciones cercanas sin precio de boletos), y entre las completas `nearest`, `cheapest`, `priciest` (filas como las
    de `recommend`, None si no hay) y `saving` (lo que se ahorra yendo a la más barata frente a la más cara)."""
    candidates = _candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                             title_norm=title_norm, formats=formats, adults=adults, children=children, seniors=seniors,
                             snacks=snacks)
    fits = [r for r in candidates if _fits(r, budget)]
    complete = sorted([r for r in fits if r["status"] == "complete"], key=_sort_key("price"))
    return {"shows": len(complete), "cinemas": len({(r["chain"], r["cinema_id"]) for r in complete}),
            "snacks_unpriced": sum(r["status"] == "snacks_unpriced" for r in fits),
            "unpriced": sum(r["status"] == "unpriced" for r in candidates),
            "nearest": min(complete, key=_sort_key("distance")) if complete else None,
            "cheapest": complete[0] if complete else None, "priciest": complete[-1] if complete else None,
            "saving": round(complete[-1]["total"] - complete[0]["total"], 2) if complete else None}


def recommend_titles(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, radius_km=5.0):
    """Películas con funciones a `radius_km` o menos en la ventana: `title_norm` (llave de título), `title`, `shows` y
    `cinemas`. Orden: más funciones primero, luego título."""
    titles = {}
    for r in _candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                         title_norm=None, formats=None, adults=1, children=0, seniors=0, snacks="none"):
        t = titles.setdefault(r["title_norm"], {"title_norm": r["title_norm"], "title": r["title"], "shows": 0, "cinemas": set()})
        t["shows"] += 1
        t["cinemas"].add((r["chain"], r["cinema_id"]))
        if r["chain"] == US:
            t["title"] = r["title"]
    out = [{**t, "cinemas": len(t["cinemas"])} for t in titles.values()]
    return sorted(out, key=lambda t: (-t["shows"], t["title_norm"]))


def recommend_catalog(conn, d0=None, d1=None, from_now=True, plaza="cdmx"):
    """Los datos para un recomendador en el navegador, con la lógica de precios de `recommend`:
    {`cinemas`, `prices`, `shows`, `packages`}.
    - `cinemas`: `chain`, `chain_label`, `cinema_id`, `cinema_name`, `lat`, `lng` y `snacks` ({producto: precio} del
      menú en sala para los productos de `SNACK_PACKAGES`; vacío si el cine no publica menú). Orden: cadena y nombre.
    - `prices`: por `chain`, `cinema_id`, `format_bucket` y `day_type`, la lectura más reciente sin eventos ni matinés:
      `adult`, `child`, `senior` (pesos) y `sampled_at`. Orden: esas cuatro llaves.
    - `shows`: las funciones de la ventana en la plaza: `chain`, `cinema_id`, `title_norm`, `title`, `date`,
      `datetime_local`, `language`, `format_bucket`, `day_type` y `movie_id` (el de la cadena). Orden: fecha, hora,
      cadena, cine y título.
    - `packages`: `SNACK_PACKAGES`, para calcular el paquete de un grupo."""
    chains = MAP_CHAINS
    pw, pp = plaza_where(plaza, chains=chains)
    cinemas = rows(conn, f"""
        SELECT chain, cinema_id, name cinema_name, lat, lng FROM cinema
        WHERE lat IS NOT NULL AND lng IS NOT NULL{pw} ORDER BY chain, name, cinema_id""", pp)
    menu = {}
    for product in sorted({p for items in SNACK_PACKAGES.values() for p, _ in items}):
        for r in concession_product_by_cinema(conn, product, plaza=plaza):
            menu.setdefault(r["cinema_id"], {})[product] = r["price"]
    for c in cinemas:
        c["chain_label"] = CHAIN_LABEL[c["chain"]]
        c["cinema_name"] = display_name(c["cinema_id"], c["cinema_name"])
        c["snacks"] = menu.get(c["cinema_id"], {}) if c["chain"] == "cinepolis" else {}
    known = {(c["chain"], c["cinema_id"]) for c in cinemas}
    prices = []
    for r in rows(conn, f"""
            WITH p AS (SELECT chain, cinema_id, format_bucket, day_type, general_cents, tickets_json, sampled_at,
                              ROW_NUMBER() OVER (PARTITION BY chain, cinema_id, format_bucket, day_type
                                                 ORDER BY sampled_at DESC, id DESC) rk
                       FROM price_sample WHERE general_cents > 0 AND {_NOT_EVENT})
            SELECT chain, cinema_id, format_bucket, day_type, general_cents, tickets_json, sampled_at FROM p WHERE rk = 1
            ORDER BY chain, cinema_id, format_bucket, day_type"""):
        if (r["chain"], r["cinema_id"]) in known:
            adult, child, senior = _ticket_prices(r["tickets_json"], r["general_cents"])
            prices.append({"chain": r["chain"], "cinema_id": r["cinema_id"], "format_bucket": r["format_bucket"],
                           "day_type": r["day_type"], "adult": adult, "child": child, "senior": senior,
                           "sampled_at": r["sampled_at"]})
    where, params, _ = _window(d0, d1, from_now, plaza=plaza, chains=chains)
    shows = rows(conn, f"""
        SELECT chain, cinema_id, title_key(title_norm) title_norm, movie_title title, date, datetime_local, language,
               {_FORMAT_CASE} format_bucket, {_DAY_TYPE_CASE} day_type, movie_id
        FROM current_showtime WHERE {where}
        ORDER BY date, datetime_local, chain, cinema_id, title_norm""", params)
    return {"cinemas": cinemas, "prices": prices, "shows": shows, "packages": SNACK_PACKAGES}
