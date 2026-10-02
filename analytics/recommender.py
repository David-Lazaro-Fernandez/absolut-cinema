"""Recomendador de funciones: las funciones cerca de un punto que caben en el presupuesto de un grupo (adultos, niños y
tercera edad), con boletos y dulcería.

Boletos: la lectura de precio más reciente del cine para el mismo formato y tipo de día, sin eventos ni matinés. Es
precio de lista, no el de esa función. El adulto paga el boleto general. Niños y tercera edad se buscan por nombre del
boleto ("MENOR", "Niños", "3ra Edad"); si la función no los tiene, pagan el general. Una función sin lectura no se
estima: queda sin precio y fuera del presupuesto. El precio de la función (`fare_json`, WTC y Papalote) manda sobre la
lectura; `price_sampled_at` es entonces la última captura de su cadena. Las cinetecas no tienen lectura: usan la tarifa pública de cada sede
(`_PUBLIC_FARES`), y `price_sampled_at` es la fecha en que se verificó.

Dulcería: el paquete (`SNACK_PACKAGES`) o el combo elegido con el menú en sala de cada cine, a los precios de ese cine
y solo con lo que ese cine vende. Cuántas personas cubre cada combo lo dice `snack_combos.csv` (versionado, revisado a
mano: el menú no lo publica), como un rango de mínimo a máximo. Solo Cinépolis publica su menú. En Cinemex y la
Cineteca el paquete queda sin precio (`snacks_total` None).
  - "best": la combinación más barata de combos y palomitas con refresco sueltos que cubre al grupo. Una combinación
    cubre a n personas si la suma de los mínimos no pasa de n y la de los máximos llega a n. Un combo "para" niños
    cubre solo a niños; uno "para" adultos (con cerveza), solo a adultos y adultos mayores.
  - "popcorn": palomitas y refresco por persona.
  - "combo_N": el combo más barato del cine para N personas, uno cada N, entre los que son para todos.

Promociones del día (`promo`), de los términos de cada cadena. Un día puede tener varias; la función lleva la que más
le conviene al grupo:
  - Cinemex Loop, en sala tradicional 2D:
    - Combo Lunes, Miércoles y Viernes: 2 boletos con palomitas y 2 refrescos, al precio de cada cine
      (`loop_combos.csv`, las listas de los términos de Loop).
    - Combo Martes Pareja ($340), Combo Jueves de Estreno ($255; $310 en los complejos Market) y los combos para 1
      persona (Individual Lunes y Miércoles, $180; Martes Individual, $240), a precio nacional.
    - El Martes 2x1 aplica en 2D, Platino incluido, sin IMAX, Atmos ni 4D: un boleto gratis por cada boleto igual que
      compras, hasta 3 por cuenta.
  - Club Cinépolis: el Combo Lunes (2 boletos, palomitas y 2 refrescos) cuesta $245 o $270 en 2D, Macro XE, Pluus y
    Junior, y $305 o $330 en IMAX y 4DX. Cinépolis no publica cuál de los dos precios tiene cada cine: va el rango. El
    Martes 2x1 aplica en casi todas las salas, VIP incluida.
  - Miércoles 2x1 de Cinépolis, comprando en la app o la web: 2D, 3D y Pluus, sin VIP ni días festivos.
Un 2x1 de Cinépolis cobra 2 boletos al precio de adulto más alto de la semana del cine y formato (el mayor de su último
precio por tipo de día). No aplican en preventa (antes del estreno del título) ni en contenido alternativo.
Casi todas piden una cuenta de Loop o de Club Cinépolis. Las dos son gratis, así que se supone que el grupo la tiene.
No se combinan: el grupo usa una sola promoción. Si le baja el costo, o le da precio a una dulcería que no lo tenía
(un combo de Cinemex), entra en boletos, dulcería y `total` (`promo["applied"]`):
  - Un combo reemplaza los boletos más caros (1 o 2, `people`) y la dulcería de esas personas, una vez. El resto paga
    su boleto y su paquete. El Combo Lunes de Cinépolis cuenta con su precio alto, así que un total que cabe en el
    presupuesto cabe seguro.
  - Un 2x1 reemplaza pares de boletos del mismo tipo, los que más ahorran, hasta su tope; la dulcería no cambia.
Con un combo del menú elegido (`combo=`) solo aplica el 2x1: el grupo ya dijo qué quiere de dulcería.

La distancia es en línea recta (haversine). En un empate, Cinemex va primero, salvo con `favor_us=False` (la demo
pública es neutral).
"""
import csv
import datetime
import functools
import json
import math
import unicodedata
from pathlib import Path
from urllib.parse import quote

from scraper import config

from .cinema_locations import _NOT_EVENT, MAP_CHAINS, display_name
from .concessions import concession_product_by_cinema
from .db import rows
from .labels import CHAIN_LABEL, PLAZA_LABEL, PROMO, PROMO_PROGRAM, SNACK_LABEL, SNACK_SINGLE, US
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
LOOP_COMBOS_PATH = Path(__file__).resolve().parent / "loop_combos.csv"
_LOOP_COLUMNS = {"cmx_lunes": "combo_lunes", "cmx_miercoles": "combo_miercoles", "cmx_viernes": "combo_viernes"}
# Las promociones no aplican en eventos especiales ni contenido alternativo. La API no marca la función: se reconoce por
# quién la distribuye o por el género. "+QueCine" es el contenido alternativo de Cinépolis.
# ponytail: lista a mano de distribuidoras; un distribuidor de eventos nuevo pasa como película hasta agregarlo aquí.
_ALTERNATIVE_DISTRIBUTORS = ("cinemex alternativo", "fathom", "the met", "trafalgar releasing", "+quecine")
_ALTERNATIVE_GENRES = ("concierto", "opera")


def _load_loop_combos():
    """{cinema_id: {promoción: precio}}; las filas sin `cinema_id` están pendientes de decidir."""
    with open(LOOP_COMBOS_PATH, encoding="utf-8") as fh:
        return {r["cinema_id"]: {key: float(r[col]) for key, col in _LOOP_COLUMNS.items() if r[col]}
                for r in csv.DictReader(fh) if r["cinema_id"]}


LOOP_COMBOS = _load_loop_combos()
# Las promociones de cada día (cadena, día; 0 = lunes); los textos de cada una están en `labels.PROMO`.
_DAY_PROMOS = {
    ("cinemex", 0): ("cmx_lunes", "cmx_individual_lunes"),
    ("cinemex", 1): ("cmx_martes_2x1", "cmx_martes_pareja", "cmx_martes_individual"),
    ("cinemex", 2): ("cmx_miercoles", "cmx_individual_miercoles"),
    ("cinemex", 3): ("cmx_jueves",),
    ("cinemex", 4): ("cmx_viernes",),
    ("cinepolis", 0): ("cp_lunes",),
    ("cinepolis", 1): ("cp_martes_2x1",),
    ("cinepolis", 2): ("cp_miercoles_2x1",),
}
# Cinemex Loop, nivel One, con precio nacional en sala tradicional 2D (términos de Loop, verificado 2026-09-29). En los
# complejos Market solo aplica el combo del jueves, con su precio Market.
_LOOP_FIXED = {"cmx_individual_lunes": 180.0, "cmx_individual_miercoles": 180.0, "cmx_martes_pareja": 340.0,
               "cmx_martes_individual": 240.0, "cmx_jueves": 255.0}
_LOOP_MARKET = {"cmx_jueves": 310.0}
_SOLO = ("cmx_individual_lunes", "cmx_individual_miercoles", "cmx_martes_individual")   # combos para 1 persona
_USES = {"cmx_martes_2x1": 3}                                                             # veces por cuenta; si no, 1
_LOOP_2X1_EXCLUDED = ("imax", "atmos", "v4d", "4dx")
# Club Cinépolis, Combo Lunes: `experience` → (precio bajo, precio alto), solo en 2D y sin VIP (verificado 2026-09-29).
# XE es Macro XE, SP es Pluus y SJ es la Sala Junior.
_COMBO_LUNES = {"": (245.0, 270.0), "XE": (245.0, 270.0), "SP": (245.0, 270.0), "SJ": (245.0, 270.0),
                "IMAX": (305.0, 330.0), "IMAXLASER": (305.0, 330.0), "4DX": (305.0, 330.0)}
_TUESDAY_2X1 = ("", "XE", "SP", "SJ", "IMAX", "IMAXLASER", "4DX")
_WEDNESDAY_2X1 = ("", "SP")
# ponytail: solo los festivos de fecha fija de la Ley Federal del Trabajo. Los móviles caen en lunes y no tocan el
# miércoles; falta el 1 de octubre de cada sexenio (2030).
_HOLIDAYS = ("01-01", "05-01", "09-16", "12-25")
# Tarifas públicas de las cinetecas, Tonalá, Cinemanía y Raly: (adulto, niño, tercera edad) por (cadena, sede). La
# fecha de verificación de cada cadena está en `_FARES_VERIFIED`.
#   - Cineteca Nacional (cinetecanacional.net/ubicacion.php): adulto $70; menores de 25, estudiantes y adultos mayores
#     $50. Martes y miércoles, $50 cualquier boleto, salvo en la Muestra, el Foro y Talento emergente (el ciclo de la
#     función, `program`).
#   - Cineteca FICG y Cineforo (cinetecaficg.com/faq): general $60 y $50; estudiantes, docentes y adultos mayores $40 y
#     $35, solo en taquilla. Los niños pagan el general. Veezi vende en línea solo el general, con los mismos precios.
#   - Cineteca Nuevo León (tarifa confirmada por el cliente; CONARTE no la publica en su sitio): general $80;
#     estudiantes, maestros e INAPAM $50. Los niños pagan el general.
#   - Cine Tonalá (ficha de cada película en cinetonala.mx): general $80, descuentos $65. Los niños pagan el general.
#   - Cinemanía (confirmada por el cliente; no la publica en su sitio): general $70 para todos.
#   - Cinemas Raly (cinemasraly.com/precios): $45 para todos; miércoles $30.
# ponytail: una función gratuita (Cinema Libre de la FICG) y el Foro al aire libre de la Cineteca Nacional ($90 por dos
# personas) pagan la tarifa de sala; la cartelera no los distingue.
_PUBLIC_FARES = {**{("cineteca", code): (70.0, 50.0, 50.0) for code in ("001", "002", "003")},
                 ("cineteca_gdl", "ficg"): (60.0, 60.0, 40.0), ("cineteca_gdl", "cineforo"): (50.0, 50.0, 35.0),
                 ("cineteca_mty", "centro-artes"): (80.0, 80.0, 50.0), ("tonala", "roma-sur"): (80.0, 80.0, 65.0),
                 ("cinemania", "loreto"): (70.0, 70.0, 70.0), ("raly", "madero"): (45.0, 45.0, 45.0)}
_FARES_VERIFIED = {"cineteca": "2026-09-30", "cineteca_gdl": "2026-09-30", "cineteca_mty": "2026-09-30", "tonala": "2026-10-02",
                   "cinemania": "2026-10-02", "raly": "2026-10-02"}
_CINETECA_DISCOUNT = 50.0
_CINETECA_DISCOUNT_DAYS = (1, 2)
_CINETECA_NO_DISCOUNT = ("muestra", "foro", "talento emergente")
# ponytail: el miércoles de Raly no aplica en preestrenos, y la cartelera no los distingue.
_RALY_WEDNESDAY = 30.0
_CHILD_WORDS = ("menor", "nino")
_SENIOR_WORDS = ("mayor", "tercera", "3 era", "3ra", "3a edad", "+60")
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


def _public_fare(r):
    """(adulto, niño, tercera edad) en pesos de la tarifa pública de la sede de la función, o None si no tiene."""
    fare = _PUBLIC_FARES.get((r["chain"], r["cinema_id"]))
    if fare and r["chain"] == "cineteca" and datetime.date.fromisoformat(r["date"]).weekday() in _CINETECA_DISCOUNT_DAYS \
            and not any(word in _plain(r["program"]) for word in _CINETECA_NO_DISCOUNT):
        return (_CINETECA_DISCOUNT,) * 3
    if fare and r["chain"] == "raly" and datetime.date.fromisoformat(r["date"]).weekday() == 2:
        return (_RALY_WEDNESDAY,) * 3
    return fare


def _menus(conn, cinema_ids):
    """{cinema_id: {producto: precio}} de los cines de Cinépolis pedidos, solo con los combos de `COMBOS` y `_SINGLE`."""
    menus = {}
    for r in concession_product_by_cinema(conn, [*COMBOS, *_SINGLE]):
        if r["cinema_id"] in cinema_ids:
            menus.setdefault(r["cinema_id"], {})[r["product_name"]] = r["price"]
    return menus


def _cover(options, n):
    """Para cada m de 0 a n: el costo mínimo de cubrir a m personas con `options` [(precio, nombre, mínimo, máximo)] y el
    último producto elegido (nombre, precio, personas antes). Cada producto se puede repetir. Si no hay combinación, el
    costo es infinito."""
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


def _promo_price(r, key):
    """(precio, precio alto o None) de la promoción `key` en la sala de la función, o None si no aplica ahí."""
    exp, traditional = (r["experience"] or "").lower(), r["format_bucket"] == "traditional"
    if key in _LOOP_COLUMNS:
        price = LOOP_COMBOS.get(r["cinema_id"], {}).get(key) if traditional else None
    elif key in _LOOP_FIXED:
        market = "market" in _plain(r["cinema_name"])
        price = (_LOOP_MARKET.get(key) if market else _LOOP_FIXED[key]) if traditional else None
    elif key == "cmx_martes_2x1":
        applies = r["format"] == "2D" and not any(word in exp for word in _LOOP_2X1_EXCLUDED)
        price = r["adult_price"] if applies else None
    else:
        vip = r["premium_tier"] == "vip"
        if key == "cp_lunes":
            return None if vip or r["format"] != "2D" else _COMBO_LUNES.get(r["experience"] or "")
        applies = (r["experience"] or "") in _TUESDAY_2X1 if key == "cp_martes_2x1" else \
            not vip and (r["experience"] or "") in _WEDNESDAY_2X1 and r["format"] in ("2D", "3D") and \
            r["date"][5:] not in _HOLIDAYS
        price = round(r["week_max_cents"] / 100, 2) if applies and r["week_max_cents"] else None
    return None if price is None else (price, None)


def _promos(r, releases):
    """Las promociones del día que aplican en la función, [{`name`, `kind`, `includes`, `program`, `program_about`,
    `condition`, `price`, `price_max`, `people`, `applied`}]; vacía si no hay."""
    keys = _DAY_PROMOS.get((r["chain"], datetime.date.fromisoformat(r["date"]).weekday()), ())
    if not keys or r["date"] < releases.get((r["chain"], r["movie_id"]), ""):
        return []
    if _plain(r["distributor"]) in _ALTERNATIVE_DISTRIBUTORS or any(g in _plain(r["genre"]) for g in _ALTERNATIVE_GENRES):
        return []
    out = []
    for key in keys:
        price = _promo_price(r, key)
        if price is None:
            continue
        name, kind, includes, program, condition = PROMO[key]
        short, about = PROMO_PROGRAM.get(program, (None, None))
        out.append({"name": name, "kind": kind, "includes": includes, "program": short, "program_about": about,
                    "condition": condition, "price": price[0], "price_max": price[1],
                    "people": 1 if key in _SOLO else 2, "applied": False, "_uses": _USES.get(key, 1),
                    "_pays_one": key == "cmx_martes_2x1"})
    return out


def _with_promo(r, promo, group, snacks, combo, rest_snacks):
    """(boletos, dulcería, desglose) del grupo si usa la promoción, o None si no se puede. `group` es [(tipo, precio del
    boleto)] de mayor a menor; `rest_snacks(adultos, niños)` da la dulcería del resto del grupo, o None sin precio. El
    combo con dos precios cuenta con el alto."""
    if promo["kind"] == "2x1":
        savings = []
        for kind in {k for k, _ in group}:
            price = next(p for k, p in group if k == kind)
            pair = price if promo["_pays_one"] else promo["price"]
            savings += [2 * price - pair] * (sum(k == kind for k, _ in group) // 2)
        used = sorted((saving for saving in savings if saving > 0), reverse=True)[:promo["_uses"]]
        return (r["tickets_total"] - sum(used), r["snacks_total"], r["snacks_items"]) if used else None
    if combo or len(group) < promo["people"]:
        return None
    rest = group[promo["people"]:]
    kids = sum(kind == "children" for kind, _ in rest)
    snacks_total, items = (0.0, []) if snacks == "none" or not rest else rest_snacks(len(rest) - kids, kids) or (None, None)
    return (promo["price_max"] or promo["price"]) + sum(price for _, price in rest), snacks_total, items


def _apply_promo(r, promos, adults, children, seniors, snacks, combo, rest_snacks):
    """La promoción que más le baja el costo al grupo, puesta en boletos, dulcería y total de `r` si le baja el costo o
    le da precio a su dulcería. Si ninguna conviene, la mejor alternativa; None si el día no tiene promociones."""
    group = sorted([("adults", r["adult_price"])] * adults + [("seniors", r["senior_price"])] * seniors +
                   [("children", r["child_price"])] * children, key=lambda g: -g[1])
    best = None
    for promo in promos:
        found = _with_promo(r, promo, group, snacks, combo, rest_snacks)
        if found is None:
            continue
        tickets, snacks_total, items = found
        total = round(tickets + snacks_total, 2) if snacks_total is not None else None
        rank = (total is None, tickets if total is None else total)
        if best is None or rank < best[0]:
            best = (rank, promo, tickets, snacks_total, items, total)
    if best is None:
        return promos[0] if promos else None
    rank, promo, tickets, snacks_total, items, total = best
    if rank < (r["total"] is None, _cost(r)):
        r["tickets_total"], r["snacks_total"], r["snacks_items"], r["total"] = round(tickets, 2), snacks_total, items, total
        promo["applied"] = True
    return promo


def _buy_url(r):
    """La página de compra en su cadena (`config.BUY_URL`), o None si la cadena no tiene plantilla."""
    template = config.BUY_URL.get(r["chain"])
    if not template or ("{movie_id}" in template and not r["movie_id"]):
        return None
    return template.format(cinema_id=quote(str(r["cinema_id"])), movie_id=quote(str(r["movie_id"])),
                           show_id=quote(str(r["show_id"])), session_id=quote(r["show_id"].rsplit(":", 1)[-1]),
                           site_token=config.VEEZI_SITE_TOKENS.get(r["cinema_id"], ""))


def _candidates(conn, lat, lng, *, d0, d1, from_now, hours, radius_km, adults, children, seniors, snacks, combo=None):
    """Todas las funciones de la ventana a `radius_km` o menos, con boletos, dulcería, costo, distancia y enlace de
    compra, sin ordenar."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, chains=MAP_CHAINS)
    dlat = radius_km / _KM_PER_DEGREE
    dlng = radius_km / (_KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    data = rows(conn, f"""
        WITH f AS (SELECT chain, show_id, cinema_id, movie_id, movie_title, title_key(title_norm) title_norm, date, genre, distributor,
                          experience, format, premium_tier, datetime_local, language, program, fare_json,
                          {_FORMAT_CASE} format_bucket, {_DAY_TYPE_CASE} day_type
                   FROM current_showtime WHERE {where}),
             p AS (SELECT chain, cinema_id, format_bucket, day_type, general_cents, tickets_json, sampled_at,
                          ROW_NUMBER() OVER (PARTITION BY chain, cinema_id, format_bucket, day_type
                                             ORDER BY sampled_at DESC, id DESC) rk
                   FROM price_sample WHERE general_cents > 0 AND {_NOT_EVENT}),
             w AS (SELECT chain, cinema_id, format_bucket, max(general_cents) week_max_cents FROM p WHERE rk = 1
                   GROUP BY chain, cinema_id, format_bucket)
        SELECT f.chain, f.show_id, f.cinema_id, c.name cinema_name, c.lat, c.lng, f.movie_id, f.movie_title title, f.title_norm,
               f.date, f.datetime_local, f.language, f.format_bucket, f.day_type, f.genre, f.distributor,
               f.experience, f.format, f.premium_tier, f.program, w.week_max_cents,
               COALESCE(json_extract(f.fare_json, '$.general_cents'), p.general_cents) general_cents,
               COALESCE(json_extract(f.fare_json, '$.tickets'), p.tickets_json) tickets_json,
               CASE WHEN f.fare_json IS NULL THEN p.sampled_at
                    ELSE (SELECT max(taken_at) FROM snapshot WHERE chain = f.chain AND ok = 1) END price_sampled_at
        FROM f JOIN cinema c ON c.chain = f.chain AND c.cinema_id = f.cinema_id
        LEFT JOIN p ON p.rk = 1 AND p.chain = f.chain AND p.cinema_id = f.cinema_id
                   AND p.format_bucket = f.format_bucket AND p.day_type = f.day_type
        LEFT JOIN w ON w.chain = f.chain AND w.cinema_id = f.cinema_id AND w.format_bucket = f.format_bucket
        WHERE c.lat BETWEEN ? AND ? AND c.lng BETWEEN ? AND ?
        ORDER BY f.chain, f.show_id""", params + [lat - dlat, lat + dlat, lng - dlng, lng + dlng])
    menus = _menus(conn, {r["cinema_id"] for r in data if r["chain"] == "cinepolis"})
    releases = {(r["chain"], r["movie_id"]): r["release"] for r in rows(conn, """
        SELECT chain, movie_id, max(release_date) release FROM presale_sample
        WHERE release_date IS NOT NULL GROUP BY chain, movie_id ORDER BY chain, movie_id""")}
    plans = {cinema_id: _snack_plan(menu, snacks, combo, adults + seniors, children) for cinema_id, menu in menus.items()} \
        if snacks != "none" or combo else {}

    @functools.lru_cache(maxsize=None)
    def rest_plan(cinema_id, grown, kids):
        return _snack_plan(menus[cinema_id], snacks, None, grown, kids) if cinema_id in menus else None
    out = []
    for r in data:
        r["distance_km"] = round(_distance_km(lat, lng, r["lat"], r["lng"]), 2)
        if r["distance_km"] > radius_km:
            continue
        r["box_office_only"] = r["chain"] in config.BOX_OFFICE_ONLY
        r["buy_url"] = None if r["box_office_only"] else _buy_url(r)
        r["cinema_name"] = display_name(r["cinema_id"], r["cinema_name"])
        general, tickets = r.pop("general_cents"), r.pop("tickets_json")
        fare = _public_fare(r)
        if fare:
            r["price_sampled_at"] = _FARES_VERIFIED[r["chain"]]
        # Una función gratis vale 0. Solo falta el precio si no hay ninguno.
        prices = fare or (_ticket_prices(tickets, general) if general is not None else None)
        if prices:
            r["adult_price"], r["child_price"], r["senior_price"] = prices
            r["tickets_total"] = round(adults * r["adult_price"] + children * r["child_price"] + seniors * r["senior_price"], 2)
        else:
            r["adult_price"] = r["child_price"] = r["senior_price"] = r["tickets_total"] = None
        menu = menus.get(r["cinema_id"], {}) if r["chain"] == "cinepolis" else {}
        plan = (0.0, []) if snacks == "none" and not combo else plans.get(r["cinema_id"]) if r["chain"] == "cinepolis" else None
        r["snacks_total"], r["snacks_items"] = plan or (None, None)
        r["snack_reference"] = round(sum(menu[p] for p in _SINGLE), 2) if all(p in menu for p in _SINGLE) else None
        r["total"] = round(r["tickets_total"] + r["snacks_total"], 2) \
            if r["tickets_total"] is not None and r["snacks_total"] is not None else None
        promos = _promos(r, releases)
        r["promo"] = _apply_promo(r, promos, adults, children, seniors, snacks, combo,
                                  lambda a, k: rest_plan(r["cinema_id"], a, k) if r["chain"] == "cinepolis" else None) \
            if r["tickets_total"] is not None else (promos[0] if promos else None)
        for promo in promos:
            del promo["_uses"], promo["_pays_one"]
        for key in ("genre", "distributor", "experience", "format", "premium_tier", "program", "week_max_cents"):
            del r[key]
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
    refresco de una persona; None sin menú), `total` (None sin precio de dulcería), `status`, `distance_km`, `movie_id`,
    `buy_url` (la página de compra en la cadena; None si no hay), `box_office_only` (la cadena vende solo en taquilla) y `promo` (la promoción del día que más le conviene al grupo,
    {`name`, `kind` ("combo" o "2x1"), `includes`, `program` ("Loop", "Club Cinépolis" o None), `program_about`,
    `condition`, `price`, `price_max`, `people`, `applied`}; `price_max` solo si la cadena publica dos precios sin decir cuál
    tiene el cine; `applied` si ya va en boletos, dulcería y `total`; None si no aplica).
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
