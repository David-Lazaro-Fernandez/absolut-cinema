"""Recomendador de funciones: las funciones cerca de un punto que caben en el presupuesto de un grupo (adultos, niños y
tercera edad), con boletos y dulcería.

Boletos: la lectura de precio más reciente del cine para el mismo formato y tipo de día, sin eventos ni matinés. Es
precio de lista, no el de esa función. El adulto paga el boleto general. Niños y tercera edad se buscan por nombre del
boleto ("MENOR", "Niños", "3ra Edad"); si la función no los tiene, pagan el general. Una función sin lectura no se
estima: queda sin precio y fuera del presupuesto.

Dulcería: el paquete (`SNACK_PACKAGES`) o el combo elegido con el menú en sala de cada cine, a los precios de ese cine
y solo con lo que ese cine vende. Cuántas personas cubre cada combo lo dice `snack_combos.csv` (versionado, revisado a
mano: el menú no lo publica), como un rango de mínimo a máximo. Solo Cinépolis publica su menú. En Cinemex y la
Cineteca el paquete queda sin precio (`snacks_total` None).
  - "best": la combinación más barata de combos y palomitas con refresco sueltos que cubre al grupo. Una combinación
    cubre a n personas si la suma de los mínimos no pasa de n y la de los máximos llega a n. Un combo "para" niños
    cubre solo a niños; uno "para" adultos (con cerveza), solo a adultos y adultos mayores.
  - "popcorn": palomitas y refresco por persona.
  - "combo_N": el combo más barato del cine para N personas, uno cada N, entre los que son para todos.

La distancia es en línea recta (haversine). En un empate, Cinemex va primero, salvo con `favor_us=False` (la demo
pública es neutral).
"""
import csv
import json
import math
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

from scraper import config

from .cinema_locations import _NOT_EVENT, MAP_CHAINS, display_name
from .concessions import concession_product_by_cinema
from .db import rows
from .labels import CHAIN_LABEL, PLAZA_LABEL, SNACK_LABEL, SNACK_SINGLE, US
from .plaza import plaza_where
from .queries import _FORMAT_CASE, _window
from .seats import _DAY_TYPE_CASE

SORTS = ("distance", "price", "time")
# "complete": boletos y dulcería con precio. "snacks_unpriced": la dulcería no tiene precio. "unpriced": los boletos
# no tienen precio. Solo "complete" compite por el presupuesto; las otras van aparte para no parecer más baratas.
STATUSES = ("complete", "snacks_unpriced", "unpriced")
SNACK_PACKAGES = tuple(SNACK_LABEL)
COMBOS_PATH = Path(__file__).resolve().parent / "snack_combos.csv"
_SINGLE = ("Palomitas", "Refresco")       # tamaño base: palomitas y refresco de una persona
_FOR = {"todos": "all", "ninos": "children", "adultos": "adults"}


def _load_combos():
    with open(COMBOS_PATH, encoding="utf-8") as fh:
        return {r["product_name"].strip(): {"min": int(r["personas_min"]), "max": int(r["personas_max"]), "for": _FOR[r["para"]]}
                for r in csv.DictReader(fh)}


COMBOS = _load_combos()
_CHILD_WORDS = ("menor", "nino")
_SENIOR_WORDS = ("mayor", "tercera", "3 era", "3ra", "3a edad")
_EARTH_KM = 6371.0
_KM_PER_DEGREE = 111.32
_AREA_MARGIN_DEG = 0.05                   # ~5 km más allá de los cines de la plaza


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


def _menus(conn, cinema_ids):
    """{cinema_id: {producto: precio}} de los cines de Cinépolis pedidos, solo con los combos de `COMBOS` y `_SINGLE`."""
    menus = {}
    for r in concession_product_by_cinema(conn, [*COMBOS, *_SINGLE]):
        if r["cinema_id"] in cinema_ids:
            menus.setdefault(r["cinema_id"], {})[r["product_name"]] = r["price"]
    return menus


def _cover(options, n):
    """El costo mínimo de cubrir exactamente a 0…n personas con `options` [(precio, nombre, mínimo, máximo)], sin tope de
    unidades: [(costo, (nombre, precio, personas antes))]; infinito si no se puede."""
    best = [(0.0, None)] + [(math.inf, None)] * n
    for m in range(1, n + 1):
        for price, name, lo, hi in options:
            for k in range(lo, min(hi, m) + 1):
                if best[m - k][0] + price < best[m][0]:
                    best[m] = (best[m - k][0] + price, (name, price, m - k))
    return best


def _units(best, m):
    """Los productos que `_cover` eligió para cubrir a `m` personas: [(nombre, precio)], uno por unidad."""
    out = []
    while m and best[m][1]:
        name, price, m = best[m][1]
        out.append((name, price))
    return out


def _plan(units):
    """(total, desglose) de [(nombre, precio)]: el desglose agrupa por producto, [{`name`, `units`, `price`}]."""
    items = {}
    for name, price in units:
        items.setdefault((name, price), 0)
        items[(name, price)] += 1
    breakdown = [{"name": name, "units": k, "price": price} for (name, price), k in sorted(items.items(), key=lambda i: (-i[0][1], i[0][0]))]
    return round(sum(price for _, price in units), 2), breakdown


def _snack_plan(menu, snacks, combo, adults, children):
    """(total, desglose) del paquete `snacks` o del combo `combo` para el grupo con el menú de un cine, o None si su menú
    no lo tiene. `adults` incluye a los adultos mayores."""
    people = adults + children
    single = round(sum(menu[p] for p in _SINGLE), 2) if all(p in menu for p in _SINGLE) else None
    if combo:
        return _plan([(combo, menu[combo])] * math.ceil(people / COMBOS[combo]["max"])) if combo in menu else None
    if snacks == "popcorn":
        return _plan([(SNACK_SINGLE, single)] * people) if single is not None else None
    if snacks.startswith("combo_"):
        size = int(snacks.removeprefix("combo_"))
        fits = sorted((menu[name], name) for name, c in COMBOS.items()
                      if name in menu and c["for"] == "all" and c["min"] <= size <= c["max"])
        return _plan([(fits[0][1], fits[0][0])] * math.ceil(people / size)) if fits else None

    def options(who):
        return sorted((menu[name], name, c["min"], c["max"]) for name, c in COMBOS.items() if name in menu and c["for"] == who)
    general = options("all") + ([(single, SNACK_SINGLE, 1, 1)] if single is not None else [])
    for_all, for_kids, for_grown = _cover(general, people), _cover(options("children"), children), _cover(options("adults"), adults)
    cost, j, i = min((for_kids[j][0] + for_grown[i][0] + for_all[people - j - i][0], j, i)
                     for j in range(children + 1) for i in range(adults + 1))
    return _plan(_units(for_kids, j) + _units(for_grown, i) + _units(for_all, people - j - i)) if cost < math.inf else None


def _slug(text):
    """"Parque Lindavista (CDMX)" → "parque-lindavista-cdmx", como los slugs de cine de Cinemex."""
    return re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", _plain(text).strip()))


def _buy_url(r):
    """La página de compra de la película en su cadena (`config.BUY_URL`), o None si la cadena no tiene plantilla."""
    template = config.BUY_URL.get(r["chain"])
    if not template or not r["movie_id"]:
        return None
    return template.format(cinema_id=quote(str(r["cinema_id"])), cinema_slug=_slug(r["cinema_name"]),
                           date=r["date"].replace("-", ""), movie_id=quote(str(r["movie_id"])))


def _candidates(conn, lat, lng, *, d0, d1, from_now, hours, radius_km, adults, children, seniors, snacks, combo=None):
    """Todas las funciones de la ventana a `radius_km` o menos, con boletos, dulcería, costo, distancia y enlace de
    compra, sin ordenar."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, chains=MAP_CHAINS)
    dlat = radius_km / _KM_PER_DEGREE
    dlng = radius_km / (_KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    data = rows(conn, f"""
        WITH f AS (SELECT chain, show_id, cinema_id, movie_id, movie_title, title_key(title_norm) title_norm, date,
                          datetime_local, language, {_FORMAT_CASE} format_bucket, {_DAY_TYPE_CASE} day_type
                   FROM current_showtime WHERE {where}),
             p AS (SELECT chain, cinema_id, format_bucket, day_type, general_cents, tickets_json, sampled_at,
                          ROW_NUMBER() OVER (PARTITION BY chain, cinema_id, format_bucket, day_type
                                             ORDER BY sampled_at DESC, id DESC) rk
                   FROM price_sample WHERE general_cents > 0 AND {_NOT_EVENT})
        SELECT f.chain, f.show_id, f.cinema_id, c.name cinema_name, c.lat, c.lng, f.movie_id, f.movie_title title, f.title_norm,
               f.date, f.datetime_local, f.language, f.format_bucket, f.day_type,
               p.general_cents, p.tickets_json, p.sampled_at price_sampled_at
        FROM f JOIN cinema c ON c.chain = f.chain AND c.cinema_id = f.cinema_id
        LEFT JOIN p ON p.rk = 1 AND p.chain = f.chain AND p.cinema_id = f.cinema_id
                   AND p.format_bucket = f.format_bucket AND p.day_type = f.day_type
        WHERE c.lat BETWEEN ? AND ? AND c.lng BETWEEN ? AND ?
        ORDER BY f.chain, f.show_id""", params + [lat - dlat, lat + dlat, lng - dlng, lng + dlng])
    menus = _menus(conn, {r["cinema_id"] for r in data if r["chain"] == "cinepolis"})
    plans = {cinema_id: _snack_plan(menu, snacks, combo, adults + seniors, children) for cinema_id, menu in menus.items()} \
        if snacks != "none" or combo else {}
    out = []
    for r in data:
        r["distance_km"] = round(_distance_km(lat, lng, r["lat"], r["lng"]), 2)
        if r["distance_km"] > radius_km:
            continue
        r["buy_url"] = _buy_url(r)
        r["cinema_name"] = display_name(r["cinema_id"], r["cinema_name"])
        general, tickets = r.pop("general_cents"), r.pop("tickets_json")
        if general:
            r["adult_price"], r["child_price"], r["senior_price"] = _ticket_prices(tickets, general)
            r["tickets_total"] = round(adults * r["adult_price"] + children * r["child_price"] + seniors * r["senior_price"], 2)
        else:
            r["adult_price"] = r["child_price"] = r["senior_price"] = r["tickets_total"] = None
        menu = menus.get(r["cinema_id"], {}) if r["chain"] == "cinepolis" else {}
        plan = (0.0, []) if snacks == "none" and not combo else plans.get(r["cinema_id"]) if r["chain"] == "cinepolis" else None
        r["snacks_total"], r["snacks_items"] = plan or (None, None)
        r["snack_reference"] = round(sum(menu[p] for p in _SINGLE), 2) if all(p in menu for p in _SINGLE) else None
        r["total"] = round(r["tickets_total"] + r["snacks_total"], 2) \
            if r["tickets_total"] is not None and r["snacks_total"] is not None else None
        r["status"] = "unpriced" if r["tickets_total"] is None else "complete" if r["total"] is not None else "snacks_unpriced"
        out.append(r)
    return out


def _cost(r):
    """Lo que se compara contra el presupuesto y ordena por precio: el total, o los boletos si la dulcería no tiene precio."""
    return r["total"] if r["total"] is not None else r["tickets_total"]


def _sort_key(sort, favor_us=True):
    us_first = (lambda r: r["chain"] != US) if favor_us else (lambda r: False)  # noqa: E731
    price = lambda r: _cost(r) if _cost(r) is not None else math.inf  # noqa: E731
    keys = {"distance": lambda r: (r["distance_km"], price(r), us_first(r), r["datetime_local"], r["show_id"]),
            "price": lambda r: (price(r), r["distance_km"], us_first(r), r["datetime_local"], r["show_id"]),
            "time": lambda r: (r["datetime_local"], r["distance_km"], price(r), us_first(r), r["show_id"])}
    return keys[sort]


def _fits(r, budget):
    """Una función entra si su costo conocido cabe: el total si está completo, los boletos si falta la dulcería."""
    return r["status"] != "unpriced" and (budget is None or _cost(r) <= budget)


def _matches(r, title_norm, formats):
    return (not title_norm or r["title_norm"] == title_norm) and (not formats or r["format_bucket"] in formats)


def _pick(found, status, budget, key, per_cinema, limit):
    """Las funciones de `status` que caben, en el orden de `key`, con a lo más `per_cinema` por cine."""
    out, taken = [], {}
    for r in sorted((r for r in found if r["status"] == status and (status == "unpriced" or _fits(r, budget))), key=key):
        k = (r["chain"], r["cinema_id"])
        if per_cinema and taken.get(k, 0) >= per_cinema:
            continue
        taken[k] = taken.get(k, 0) + 1
        out.append(r)
    return out[:limit]


def _summary(found, budget, favor_us=True):
    fits = [r for r in found if _fits(r, budget)]
    complete = sorted([r for r in fits if r["status"] == "complete"], key=_sort_key("price", favor_us))
    return {"shows": len(complete), "cinemas": len({(r["chain"], r["cinema_id"]) for r in complete}),
            "snacks_unpriced": sum(r["status"] == "snacks_unpriced" for r in fits),
            "unpriced": sum(r["status"] == "unpriced" for r in found),
            "nearest": min(complete, key=_sort_key("distance", favor_us)) if complete else None,
            "cheapest": complete[0] if complete else None, "priciest": complete[-1] if complete else None,
            "saving": round(complete[-1]["total"] - complete[0]["total"], 2) if complete else None}


def _titles(found):
    titles = {}
    for r in found:
        t = titles.setdefault(r["title_norm"], {"title_norm": r["title_norm"], "title": r["title"], "shows": 0, "cinemas": set()})
        t["shows"] += 1
        t["cinemas"].add((r["chain"], r["cinema_id"]))
        if r["chain"] == US:
            t["title"] = r["title"]
    out = [{**t, "cinemas": len(t["cinemas"])} for t in titles.values()]
    return sorted(out, key=lambda t: (-t["shows"], t["title_norm"]))


def _sites(found, budget):
    """Un punto por edificio con funciones que caben: el complejo y su sala Platino o VIP comparten coordenadas."""
    sites = {}
    for r in found:
        if not _fits(r, budget):
            continue
        s = sites.setdefault((r["lat"], r["lng"]), {"lat": r["lat"], "lng": r["lng"], "distance_km": r["distance_km"],
                                                     "cinemas": [], "shows": 0})
        cinema = {"chain": r["chain"], "chain_label": CHAIN_LABEL[r["chain"]], "cinema_id": r["cinema_id"],
                  "cinema_name": r["cinema_name"]}
        if cinema not in s["cinemas"]:
            s["cinemas"].append(cinema)
        s["shows"] += 1
    for s in sites.values():
        s["cinemas"].sort(key=lambda c: (c["chain"], c["cinema_name"]))
    return sorted(sites.values(), key=lambda s: (s["distance_km"], s["lat"], s["lng"]))


def recommend(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, adults=2, children=0, seniors=0,
              snacks="none", combo=None, budget=None, radius_km=5.0, title_norm=None, formats=None, status="complete",
              sort="distance", per_cinema=None, limit=40):
    """Funciones a `radius_km` o menos de (`lat`, `lng`) para un grupo de `adults`, `children` y `seniors` con el
    paquete `snacks` (clave de `SNACK_PACKAGES`) o el combo `combo` (nombre de `COMBOS`, uno cada su máximo de
    personas; manda sobre `snacks`). Solo devuelve las del `status` pedido (ver `STATUSES`). `budget`
    (None = sin tope) se aplica al `total` en "complete" y a los boletos en "snacks_unpriced". `title_norm` y `formats`
    acotan la búsqueda.
    Por fila: `chain`, `show_id`, `cinema_id`, `cinema_name`, `lat`, `lng`, `title`, `title_norm`, `date`,
    `datetime_local`, `language`, `format_bucket`, `day_type`, `price_sampled_at`, `adult_price`, `child_price`,
    `senior_price`, `tickets_total`, `snacks_total` (0 sin paquete, None sin precio), `snacks_items` (el desglose,
    [{`name`, `units`, `price`}]; None sin precio), `snack_reference` (palomitas y
    refresco de una persona; None sin menú), `total` (None sin precio de dulcería), `status`, `distance_km`, `movie_id`
    y `buy_url` (la página de compra en la cadena; None si no hay).
    Orden según `sort` ("distance", "price" o "time"). `per_cinema` limita las funciones de cada cine."""
    found = [r for r in _candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                                    adults=adults, children=children, seniors=seniors, snacks=snacks, combo=combo)
             if _matches(r, title_norm, formats)]
    return _pick(found, status, budget, _sort_key(sort), per_cinema, limit)


def recommend_summary(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, adults=2, children=0, seniors=0,
                      snacks="none", combo=None, budget=None, radius_km=5.0, title_norm=None, formats=None):
    """Resumen de lo que `recommend` encuentra, sin límite: `shows` y `cinemas` (funciones de costo completo que caben y
    sus cines), `snacks_unpriced` (funciones cuyos boletos caben pero sin precio del paquete de dulcería), `unpriced`
    (funciones cercanas sin precio de boletos), y entre las completas `nearest`, `cheapest`, `priciest` (filas como las
    de `recommend`, None si no hay) y `saving` (lo que se ahorra yendo a la más barata frente a la más cara)."""
    found = [r for r in _candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                                    adults=adults, children=children, seniors=seniors, snacks=snacks, combo=combo)
             if _matches(r, title_norm, formats)]
    return _summary(found, budget)


def recommend_titles(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, radius_km=5.0):
    """Películas con funciones a `radius_km` o menos en la ventana: `title_norm` (llave de título), `title`, `shows` y
    `cinemas`. Orden: más funciones primero, luego título."""
    return _titles(_candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                               adults=1, children=0, seniors=0, snacks="none"))


def recommend_search(conn, lat, lng, d0=None, d1=None, from_now=True, hours=None, adults=2, children=0, seniors=0,
                     snacks="none", combo=None, budget=None, radius_km=5.0, title_norm=None, formats=None, sort="distance",
                     per_cinema=3, limit=40, favor_us=True, site=None):
    """Todo lo que una búsqueda necesita, en una sola lectura de la base: {`summary`, `complete`, `snacks_unpriced`,
    `unpriced`, `sites`, `titles`}. Los parámetros son los de `recommend`.
    - `summary`: lo de `recommend_summary`. `complete`, `snacks_unpriced` y `unpriced`: las filas de `recommend` de
      cada estado, con `per_cinema` y `limit`.
    - `sites`: un punto por edificio con funciones que caben: `lat`, `lng`, `distance_km`, `shows` y `cinemas`
      (`chain`, `chain_label`, `cinema_id`, `cinema_name`). Orden: distancia.
    - `titles`: lo de `recommend_titles`, sin el filtro de película ni de formato.
    `favor_us=False` resuelve los empates sin favorecer a Cinemex. `site=(lat, lng)` deja solo las funciones de ese
    edificio, sin tope por cine ni límite."""
    everything = _candidates(conn, lat, lng, d0=d0, d1=d1, from_now=from_now, hours=hours, radius_km=radius_km,
                             adults=adults, children=children, seniors=seniors, snacks=snacks, combo=combo)
    found = [r for r in everything if _matches(r, title_norm, formats)]
    if site is not None:
        found = [r for r in found if (r["lat"], r["lng"]) == tuple(site)]
        per_cinema = limit = None
    key = _sort_key(sort, favor_us)
    return {"summary": _summary(found, budget, favor_us),
            **{status: _pick(found, status, budget, key, per_cinema, limit) for status in STATUSES},
            "sites": _sites(found, budget), "titles": _titles(everything)}


def recommend_options(conn, plazas=("cdmx", "gdl", "mty"), d0=None, d1=None, from_now=True):
    """Lo que un buscador necesita antes de buscar: {`plazas`, `dates`, `formats`, `cinemas`, `snacks`, `combos`}.
    - `plazas`: `plaza`, `label`, `lat`, `lng` (centro de sus cines) y `bbox` ([oeste, sur, este, norte], la caja de sus
      cines con `_AREA_MARGIN_DEG` de margen). Solo las que tienen cines.
    - `dates`: `date` y `day_type` de los días con funciones en la ventana. Orden: fecha.
    - `formats`: las cubetas de formato de esas funciones, en orden alfabético.
    - `cinemas`: `chain`, `chain_label`, `cinema_name`, `lat` y `lng` de los cines con coordenadas. Orden: cadena y nombre.
    - `snacks`: las claves de `SNACK_PACKAGES`.
    - `combos`: `name`, `min`, `max` (personas) y `for` ("all", "children" o "adults") de cada combo de `COMBOS`.
      Orden: nombre."""
    out = {"plazas": [], "dates": {}, "formats": set(), "cinemas": [], "snacks": list(SNACK_PACKAGES),
           "combos": [{"name": name, **c} for name, c in sorted(COMBOS.items())]}
    for plaza in plazas:
        pw, pp = plaza_where(plaza, chains=MAP_CHAINS)
        cinemas = rows(conn, f"""
            SELECT chain, cinema_id, name cinema_name, lat, lng FROM cinema
            WHERE lat IS NOT NULL AND lng IS NOT NULL{pw} ORDER BY chain, name, cinema_id""", pp)
        if not cinemas:
            continue
        lats, lngs, m = [c["lat"] for c in cinemas], [c["lng"] for c in cinemas], _AREA_MARGIN_DEG
        out["plazas"].append({"plaza": plaza, "label": PLAZA_LABEL.get(plaza, plaza),
                              "lat": round(sum(lats) / len(lats), 4), "lng": round(sum(lngs) / len(lngs), 4),
                              "bbox": [round(min(lngs) - m, 2), round(min(lats) - m, 2),
                                       round(max(lngs) + m, 2), round(max(lats) + m, 2)]})
        out["cinemas"] += [{"chain": c["chain"], "chain_label": CHAIN_LABEL[c["chain"]],
                            "cinema_name": display_name(c["cinema_id"], c["cinema_name"]), "lat": c["lat"], "lng": c["lng"]}
                           for c in cinemas]
        where, params, _ = _window(d0, d1, from_now, plaza=plaza, chains=MAP_CHAINS)
        for r in rows(conn, f"""SELECT DISTINCT date, {_DAY_TYPE_CASE} day_type, {_FORMAT_CASE} format_bucket
                                FROM current_showtime WHERE {where}""", params):
            out["dates"][r["date"]] = r["day_type"]
            out["formats"].add(r["format_bucket"])
    out["dates"] = [{"date": d, "day_type": t} for d, t in sorted(out["dates"].items())]
    out["formats"] = sorted(out["formats"])
    out["cinemas"].sort(key=lambda c: (c["chain"], c["cinema_name"], c["lat"], c["lng"]))
    return out
