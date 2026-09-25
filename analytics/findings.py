"""Capa 1 y conclusiones de Capa 2 del dashboard: hallazgos redactados como decisión.

Cada hallazgo sale de las mismas consultas que el resto del dashboard y se redacta solo si cruza un
umbral que lo hace relevante para una decisión de programación esta semana. Nunca hay cifras fijas
aquí: si el dato no existe, el hallazgo no aparece. Hablamos en primera persona como Cinemex.

`findings()` devuelve hasta `top` dicts {topic, title, body, action, support: [{label, value, cmx}], strength, as_of}:
se evalúan todas las reglas y entran las más fuertes (`strength` = brecha / umbral). `as_of` es la fecha del dato
muestreado que sostiene el hallazgo (None si solo usa la cartelera vigente).
`conclusions()` devuelve {peliculas, peliculas_note, franjas, formatos}: la frase que abre cada
sección de evidencia."""
from datetime import datetime, timedelta, timezone

from .concessions import concession_basket
from .db import rows
from .delivery import delivery_compare, delivery_summary
from .labels import (
    CHAIN_LABEL,
    DAY_TYPE_LABEL,
    FORMAT_LABEL,
    FULL_DAY,
    SLOT_SHORT,
    SLOTS,
    THEM,
    US,
    WEEKDAY_LABEL,
    date_es,
)
from .presale import presale_compare, presale_ranking
from .queries import (
    concentration,
    heatmap_day_slot,
    is_full_day,
    kpis,
    mix,
    movies_by_chain,
    now_local,
    programming_moves,
    showtimes_by_slot,
    today,
)
from .seats import effective_ticket_price, occupancy_by_title, offered_by_title, prices
from .summary import general_summary

THEM_NAME = CHAIN_LABEL[THEM]

# Umbrales (en puntos porcentuales salvo que se indique) a partir de los cuales una diferencia
# merece una tarjeta de Capa 1.
TITLE_SEATS_MIN_PP = 1.5        # diferencia entre Δ funciones y Δ butacas de un título
TITLE_MIN_SHARE = 2.0           # % mínimo de la parrilla de alguna cadena para considerar un título
TOP3_MIN_PP = 3.0
SLOT_MIN_PP = 1.0
FORMAT_MIN_PP = 5.0
EXCLUSIVE_MIN_TITLES = 3
EXCLUSIVE_MIN_SHOWS = 20
CONCESSION_MIN_PCT = 10.0       # brecha mediana de precio en la canasta comparable de dulcería a domicilio
MOVE_MIN_PP = 1.0               # cambio de share de un título en lo que falta de la semana
MOVE_MIN_SHOWS = 30             # y al menos estas funciones netas, para que un título chico no cruce solo por pp
PRICE_MIN_PCT = 10.0            # brecha del boleto promedio ponderado por la parrilla de cada cadena
PRICE_MIN_PRICED = 50.0         # % mínimo de funciones con precio muestreado para afirmar un promedio
DEMAND_MIN_DEV = 0.3            # un título vende 30 % más (o menos) de lo esperado para su horario en Cinépolis
DEMAND_MIN_SAMPLES = 20         # planos tras el inicio del título en la ventana de muestreo
DEMAND_MIN_SHARE = 1.0          # % de la parrilla vigente de Cinépolis: el título tiene que seguir en su cartelera
PRESALE_MIN_RATIO = 2.0         # el título que más vende en preventa le saca al menos el doble al segundo
PRESALE_MIN_SHOWS = 10          # funciones del panel vigente para comparar un título
PRESALE_GAP_MIN_PP = 10.0       # brecha de % del aforo vendido en un mismo título entre cadenas
PRESALE_EXCLUSIVE_MIN_PCT = 40.0  # % del aforo vendido de una preventa exclusiva de Cinépolis que ya merece atención
PRICE_MIN_CINEMAS = 5           # cines muestreados por cadena para citar una combinación de formato y tipo de día

# Ventanas de muestreo: el precio se renueva una vez por semana por cine, formato y tipo de día, así que 14 días cubren
# una vuelta completa con holgura; la ocupación se mide cada hora y una semana de cine basta para leer la demanda.
PRICE_SAMPLE_DAYS = 14
DEMAND_SAMPLE_DAYS = 7
# La dulcería a domicilio se captura a diario: un dato más viejo ya no describe el precio de hoy.
CONCESSION_MAX_AGE_DAYS = 3
# El formato es una diferencia de sala, no de semana: solo desplaza a otro hallazgo si la brecha es muy grande.
_STRUCTURAL_WEIGHT = 0.5


def _pp(v):
    return f"{v:+.1f} pp".replace("-", "−")


def _pct(v):
    return f"{v:.0f} %"


def _short(title, n=32):
    t = title.strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _slot_phrase(key):
    """'despues_21' -> 'después de las 9 PM'; 'de_15_a_18' -> 'de 3 a 6 PM'."""
    label = SLOT_SHORT[key]
    if key == "despues_21":
        return "después de las 9 PM"
    if key == "antes_10":
        return "antes de las 10 AM"
    return "de " + label.replace(" – ", " a ").replace("P.M.", "PM").replace("A.M.", "AM")


def _slot_name(key):
    return SLOT_SHORT[key].replace("P.M.", "PM").replace("A.M.", "AM")


def _title_finding(conn, d0, d1, hours=None, plaza=None):
    """¿Dónde la apuesta por sala (butacas) cuenta otra historia que la apuesta por funciones?"""
    movies = movies_by_chain(conn, d0, d1, limit=60, hours=hours, plaza=plaza)
    seats = {c: {r["title_norm"]: r for r in offered_by_title(conn, d0, d1, limit=60, chain=c, hours=hours, plaza=plaza)} for c in (US, THEM)}
    if not seats[US] or not seats[THEM]:
        return None
    best, score = None, 0
    for m in movies:
        if not (m["shows_cinemex"] and m["shows_cinepolis"]):
            continue
        if max(m["share_cinemex"], m["share_cinepolis"]) < TITLE_MIN_SHARE:
            continue
        su, st_ = seats[US].get(m["title_norm"]), seats[THEM].get(m["title_norm"])
        if not su or not st_:
            continue
        sg = m["share_cinemex"] - m["share_cinepolis"]
        kg = su["share_seats"] - st_["share_seats"]
        s = abs(kg - sg)
        if s > score:
            best, score = (m, su, st_, sg, kg), s
    if not best or score < TITLE_SEATS_MIN_PP:
        return None
    m, su, st_, sg, kg = best
    t = _short(m["title"])
    support = [
        {"label": "Parrilla Cinemex", "value": _pct(m["share_cinemex"]), "cmx": True},
        {"label": f"Parrilla {THEM_NAME}", "value": _pct(m["share_cinepolis"]), "cmx": False},
        {"label": "Butacas Cinemex", "value": _pct(su["share_seats"]), "cmx": True},
        {"label": f"Butacas {THEM_NAME}", "value": _pct(st_["share_seats"]), "cmx": False},
    ]
    if sg > 0 and kg < 0:
        title = f"{THEM_NAME} apuesta a {t} con salas grandes; nosotros con más funciones. Su butaca rinde más."
        body = (f"Le damos {sg:.1f} pp más de parrilla, pero ellos lo programan en salas de {st_['avg_seats']:.0f} asientos "
                f"frente a nuestras {su['avg_seats']:.0f}: con menos funciones ponen {abs(kg):.1f} pp más de sus butacas en juego.")
        action = f"Decisión: ¿mover {t} a salas más grandes o sostener la ventaja por frecuencia?"
    elif sg < 0 and kg > 0:
        title = f"{THEM_NAME} da más funciones a {t}, pero nosotros ponemos más butacas: la apuesta real es nuestra."
        body = (f"Ellos le dan {abs(sg):.1f} pp más de parrilla en salas de {st_['avg_seats']:.0f} asientos; nosotros la "
                f"programamos en salas de {su['avg_seats']:.0f} y ponemos {kg:.1f} pp más de nuestras butacas.")
        action = f"Decisión: confirmar con ocupación que {t} llena salas grandes antes de la siguiente semana de cine"
    elif abs(kg) > abs(sg):
        who_us = sg >= 0
        title = (f"{t} es nuestra mayor apuesta y en butacas lo es aún más: {kg:+.1f} pp frente a {THEM_NAME}."
                 if who_us else
                 f"{THEM_NAME} apuesta a {t} más de lo que parece: {abs(kg):.1f} pp más de butacas, no solo {abs(sg):.1f} pp de funciones.")
        body = (f"{'Le damos' if who_us else 'Le dan'} {abs(sg):.1f} pp más de parrilla y {'la programamos' if who_us else 'la programan'} "
                f"en salas de {(su if who_us else st_)['avg_seats']:.0f} asientos frente a {(st_ if who_us else su)['avg_seats']:.0f} "
                f"del otro lado: la diferencia en butacas ofertadas es {abs(kg):.1f} pp.")
        action = (f"Decisión: confirmar con ocupación que {t} sostiene salas grandes" if who_us else
                  f"Decisión: ¿subir {t} a salas más grandes para no ceder la apuesta?")
    else:
        who_us = sg >= 0
        title = (f"Apostamos a {t} por frecuencia, no por sala: {sg:+.1f} pp de funciones pero solo {kg:+.1f} pp de butacas."
                 if who_us else
                 f"{THEM_NAME} apuesta a {t} por frecuencia: {abs(sg):.1f} pp más de funciones pero solo {abs(kg):.1f} pp más de butacas.")
        body = (f"{'Nuestras' if who_us else 'Sus'} salas para {t} promedian {(su if who_us else st_)['avg_seats']:.0f} asientos frente a "
                f"{(st_ if who_us else su)['avg_seats']:.0f}: la ventaja en funciones se diluye al medirla en butacas.")
        action = (f"Decisión: ¿concentrar {t} en menos funciones y salas más grandes?" if who_us else
                  f"Decisión: sostener la posición en {t}; su ventaja es menor de lo que parece")
    support.append({"label": "Sala prom. Cinemex", "value": f"{su['avg_seats']:.0f} asientos", "cmx": True})
    support.append({"label": f"Sala prom. {THEM_NAME}", "value": f"{st_['avg_seats']:.0f} asientos", "cmx": False})
    return {"topic": "titulo", "title": title, "body": body, "action": action, "support": support[:4] + support[4:6],
            "strength": score / TITLE_SEATS_MIN_PP}


def _concentration_finding(conn, d0, d1, movies, hours=None, plaza=None):
    cc = {r["chain"]: r for r in concentration(conn, d0, d1, hours=hours, plaza=plaza)}
    if US not in cc or THEM not in cc:
        return None
    cu, ct = cc[US], cc[THEM]
    gap = cu["top3_pct"] - ct["top3_pct"]
    if abs(gap) < TOP3_MIN_PP:
        return None
    shared_top = sorted([m for m in movies if m["shows_cinemex"]], key=lambda m: -m["shows_cinemex"])[:2]
    names = " o ".join(_short(m["title"], 24) for m in shared_top) or "los estrenos"
    only_them = [m for m in movies if not m["shows_cinemex"] and m["shows_cinepolis"] >= EXCLUSIVE_MIN_SHOWS]
    dt = ct["titles"] - cu["titles"]
    if gap > 0:
        title = (f"Concentramos la apuesta: 3 títulos se llevan {'casi la mitad' if cu['top3_pct'] >= 45 else _pct(cu['top3_pct'])} "
                 f"de nuestra parrilla" + (f", con {dt} títulos menos en cartelera." if dt > 0 else "."))
        body = (f"Coherente si la ventana de estrenos es fuerte; caro si {names} se enfrían. {THEM_NAME} reparte más"
                + (f" y cubre {len(only_them)} títulos que no tenemos." if only_them else "."))
        action = "Decisión: validar la concentración contra el calendario de estrenos"
    else:
        title = (f"{THEM_NAME} concentra más que nosotros: sus 3 títulos principales pesan {_pct(ct['top3_pct'])} de su parrilla "
                 f"frente a nuestro {_pct(cu['top3_pct'])}.")
        body = ("Cubrimos más ancho" + (f" con {-dt} títulos más" if dt < 0 else "") +
                "; rinde si los títulos medianos venden, y cuesta si la taquilla está en los tres grandes.")
        action = "Decisión: ¿recortar cola larga para reforzar los tres títulos principales?"
    return {"topic": "concentracion", "title": title, "body": body, "action": action, "strength": abs(gap) / TOP3_MIN_PP, "support": [
        {"label": "Top 3 Cinemex", "value": _pct(cu["top3_pct"]), "cmx": True},
        {"label": f"Top 3 {THEM_NAME}", "value": _pct(ct["top3_pct"]), "cmx": False},
        {"label": "Títulos Cinemex", "value": f"{cu['titles']}", "cmx": True},
        {"label": f"Títulos {THEM_NAME}", "value": f"{ct['titles']}", "cmx": False},
    ]}


def _slot_finding(conn, d0, d1, hours=None, plaza=None):
    if not is_full_day(hours):
        return None   # con la franja recortada, la "franja ganadora" pierde el sentido comparativo
    slots = {r["chain"]: r for r in showtimes_by_slot(conn, d0, d1, plaza=plaza)}
    if US not in slots or THEM not in slots or not slots[US]["total"] or not slots[THEM]["total"]:
        return None
    su, st_ = slots[US], slots[THEM]
    gaps = {k: 100.0 * su[k] / su["total"] - 100.0 * st_[k] / st_["total"] for k, *_ in SLOTS}
    key = max(gaps, key=lambda k: abs(gaps[k]))
    g = gaps[key]
    if abs(g) < SLOT_MIN_PP:
        return None
    peak_us = max(SLOTS, key=lambda s: su[s[0]])[0]
    peak_them = max(SLOTS, key=lambda s: st_[s[0]])[0]
    pct_us = 100.0 * su[peak_us] / su["total"]
    pct_them = 100.0 * st_[peak_them] / st_["total"]
    source = max((k for k in gaps if k != key), key=lambda k: gaps[k]) if g < 0 else min((k for k in gaps if k != key), key=lambda k: gaps[k])
    evening = key in ("de_18_a_21", "despues_21")
    if g < 0:
        title = f"{THEM_NAME} nos gana {_slot_phrase(key)}: pone {abs(g):.1f} pp más de su parrilla ahí."
        body = (f"Nuestra franja más cargada es {_slot_name(peak_us)} ({pct_us:.0f} % de las funciones); la suya es "
                f"{_slot_name(peak_them)} ({pct_them:.0f} %)."
                + (" En la franja de mayor taquilla entramos con menos oferta relativa." if evening else ""))
        action = f"Decisión: ¿reasignar funciones de {_slot_name(source)} a {_slot_name(key)}?"
    else:
        title = f"Ganamos {_slot_phrase(key)}: ponemos {g:.1f} pp más de nuestra parrilla que {THEM_NAME}."
        body = (f"Nuestra franja más cargada es {_slot_name(peak_us)} ({pct_us:.0f} % de las funciones); la de {THEM_NAME} es "
                f"{_slot_name(peak_them)} ({pct_them:.0f} %)."
                + ("" if evening else f" Donde más cedemos es {_slot_phrase(source)} ({gaps[source]:+.1f} pp)."))
        action = (f"Decisión: sostener la ventaja {_slot_phrase(key)} y vigilar su ocupación" if evening else
                  f"Decisión: ¿mover parte de la oferta de {_slot_name(key)} a {_slot_name(source)}?")
    support = []
    hm = heatmap_day_slot(conn, d0, d1, plaza=plaza)
    days = sorted({r["weekday"] for r in hm})
    if 1 < len(days) <= 2:
        for r in hm:
            if r["slot"] == key:
                d = (r["share_cinemex"] or 0) - (r["share_cinepolis"] or 0)
                support.append({"label": f"Δ {_slot_name(key)} ({WEEKDAY_LABEL[r['weekday']][:3].lower()})", "value": _pp(d), "cmx": d > 0})
    else:
        support.append({"label": f"Δ {_slot_name(key)}", "value": _pp(g), "cmx": g > 0})
    support.append({"label": "Pico Cinemex", "value": f"{_slot_name(peak_us)} · {pct_us:.0f} %", "cmx": True})
    support.append({"label": f"Pico {THEM_NAME}", "value": f"{_slot_name(peak_them)} · {pct_them:.0f} %", "cmx": False})
    return {"topic": "franjas", "title": title, "body": body, "action": action, "support": support[:4], "strength": abs(g) / SLOT_MIN_PP}


def _format_finding(conn, d0, d1, kp, hours=None, plaza=None):
    mx = {(r["dimension"], r["chain"], r["bucket"]): r["share"] for r in mix(conn, d0, d1, hours=hours, plaza=plaza)}
    gaps = [(mx.get(("format", US, b), 0) - mx.get(("format", THEM, b), 0), b) for b in FORMAT_LABEL if b != "traditional"]
    g, b = max(gaps, key=lambda x: abs(x[0]))
    if abs(g) < FORMAT_MIN_PP:
        return None
    u, t = mx.get(("format", US, b), 0), mx.get(("format", THEM, b), 0)
    us, them = kp.get(US), kp.get(THEM)
    sub = (f" Ellos subtitulan más ({them['pct_subtitled']:.0f} % frente a {us['pct_subtitled']:.0f} %)."
           if us and them and them["pct_subtitled"] > us["pct_subtitled"] + 1 else
           f" Nosotros subtitulamos más ({us['pct_subtitled']:.0f} % frente a {them['pct_subtitled']:.0f} %)."
           if us and them and us["pct_subtitled"] > them["pct_subtitled"] + 1 else "")
    if g > 0:
        title = f"Nuestra diferencia estructural es {FORMAT_LABEL[b]}: {_pct(u)} de nuestras funciones frente a {_pct(t)} en {THEM_NAME}."
        action = f"Decisión: confirmar que la oferta {FORMAT_LABEL[b]} se traduce en ocupación y precio"
    else:
        title = f"{THEM_NAME} nos supera en {FORMAT_LABEL[b]}: {_pct(t)} de sus funciones frente a {_pct(u)} nuestras."
        action = f"Decisión: ¿ampliar la oferta {FORMAT_LABEL[b]} donde tenemos sala?"
    body = "Es una diferencia de sala, no de semana: cambia poco de un periodo a otro." + sub
    return {"topic": "formato", "title": title, "body": body, "action": action,
            "strength": _STRUCTURAL_WEIGHT * abs(g) / FORMAT_MIN_PP, "support": [
        {"label": f"{FORMAT_LABEL[b]} Cinemex", "value": _pct(u), "cmx": True},
        {"label": f"{FORMAT_LABEL[b]} {THEM_NAME}", "value": _pct(t), "cmx": False},
        {"label": "Subtituladas Cinemex", "value": _pct(us["pct_subtitled"]) if us else "—", "cmx": True},
        {"label": f"Subtituladas {THEM_NAME}", "value": _pct(them["pct_subtitled"]) if them else "—", "cmx": False},
    ]}


def _concession_gap(conn):
    """Brecha mediana (%) Cinépolis vs Cinemex en las cubetas comparables de dulcería a domicilio, las cubetas y la
    fecha de la lectura más reciente (ISO UTC)."""
    as_of = rows(conn, "SELECT MAX(sampled_at) t FROM delivery_price")[0]["t"]
    cmp_ = [r for r in delivery_compare(conn) if r["delta_pct"] is not None]
    if not cmp_:
        return None, [], as_of
    gaps = sorted(r["delta_pct"] for r in cmp_)
    return gaps[len(gaps) // 2], cmp_, as_of


def _local_date(iso_utc):
    return datetime.fromisoformat(iso_utc).astimezone(now_local().tzinfo).date().isoformat()


def _is_fresh(as_of, max_age_days):
    return bool(as_of) and datetime.fromisoformat(as_of) >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _concession_finding(conn):
    gap, cmp_, as_of = _concession_gap(conn)
    if gap is None or abs(gap) < CONCESSION_MIN_PCT or not _is_fresh(as_of, CONCESSION_MAX_AGE_DAYS):
        return None
    basket = {r["product_name"]: r for r in concession_basket(conn)}
    pop = basket.get("Palomitas")
    single = [r["pct_single_price"] for r in delivery_summary(conn) if r["chain"] == US and r["pct_single_price"] is not None]
    by = {r["bucket"]: r for r in cmp_}
    if gap > 0:
        title = f"{THEM_NAME} cobra {gap:.0f} % más que nosotros en la dulcería a domicilio, y en sala fija el precio por complejo."
        action = "Decisión: ¿sostener el precio único como argumento de valor o probar precio por zona en la canasta básica?"
    else:
        title = f"Nuestra dulcería a domicilio es {abs(gap):.0f} % más cara que la de {THEM_NAME}."
        action = "Decisión: revisar la canasta básica frente a la suya antes de la siguiente campaña."
    body = ("Nuestra lista es una sola en toda la ciudad" + (f" ({single[0]:.0f} % de los productos con un solo precio)" if single else "") + "; "
            + (f"{THEM_NAME} mueve la canasta por complejo: palomitas de ${pop['min_price']:,.0f} a ${pop['max_price']:,.0f} en "
               f"{int(pop['distinct_prices'])} niveles de precio." if pop else f"{THEM_NAME} fija precio por complejo."))
    support = []
    for key, label in (("combo_basico", "Combo básico"), ("combo_nachos", "Combo nachos"), ("nachos", "Nachos"), ("refresco", "Refresco")):
        r = by.get(key)
        if r and r["cinemex_median"] and r["cinepolis_median"]:
            support.append({"label": label, "value": f"${r['cinemex_median']:,.0f} vs ${r['cinepolis_median']:,.0f}", "cmx": r["cinemex_median"] <= r["cinepolis_median"]})
    if pop:
        support.append({"label": f"Niveles de precio {THEM_NAME}", "value": f"{int(pop['distinct_prices'])} en {int(pop['cinemas'])} complejos", "cmx": False})
    return {"topic": "dulceria", "title": title, "body": body, "action": action, "support": support[:5],
            "strength": abs(gap) / CONCESSION_MIN_PCT, "as_of": as_of}


def _exclusive_finding(movies):
    only_them = [m for m in movies if not m["shows_cinemex"] and m["shows_cinepolis"] >= EXCLUSIVE_MIN_SHOWS]
    only_us = [m for m in movies if not m["shows_cinepolis"] and m["shows_cinemex"] >= EXCLUSIVE_MIN_SHOWS]
    if len(only_them) < EXCLUSIVE_MIN_TITLES:
        return None
    names = ", ".join(_short(m["title"], 26) for m in only_them[:3])
    title = f"{THEM_NAME} exhibe {len(only_them)} títulos que no tenemos; el mayor se lleva {_pct(only_them[0]['share_cinepolis'])} de su parrilla."
    body = f"{names}" + (f" y {len(only_them) - 3} más." if len(only_them) > 3 else ".") + \
           (f" Nosotros tenemos {len(only_us)} exclusivas." if only_us else "")
    return {"topic": "exclusivas", "title": title, "body": body, "strength": len(only_them) / EXCLUSIVE_MIN_TITLES,
            "action": "Decisión: ¿alguna exclusiva de Cinépolis merece sala esta semana?",
            "support": [{"label": f"Solo {THEM_NAME}", "value": f"{len(only_them)} títulos", "cmx": False},
                        {"label": "Solo Cinemex", "value": f"{len(only_us)} títulos", "cmx": True}] +
                       [{"label": _short(m["title"], 22), "value": _pct(m["share_cinepolis"]), "cmx": False} for m in only_them[:2]]}


def _moves_finding(conn, d0, d1, hours=None, plaza=None):
    """El título al que una cadena le cambió más la parrilla de lo que falta de la semana; primero Cinépolis."""
    moves = programming_moves(conn, d0, d1, hours=hours, plaza=plaza)
    big = [m for m in moves if abs(m["delta_pp"]) >= MOVE_MIN_PP and abs(m["shows_now"] - m["shows_then"]) >= MOVE_MIN_SHOWS]
    pick = next((m for m in big if m["chain"] == THEM), None) or next((m for m in big if m["chain"] == US), None)
    if not pick:
        return None
    them = pick["chain"] == THEM
    t = _short(pick["title"])
    net = pick["shows_now"] - pick["shows_then"]
    since = date_es(_local_date(pick["since"]), with_year=False)
    who = THEM_NAME if them else "Nosotros"
    verb = ("le sumó" if them else "le sumamos") if net > 0 else ("le quitó" if them else "le quitamos")
    title = (f"Desde el {since}, {who.lower() if not them else who} {verb} {abs(net):,} funciones a {t}: pasó de "
             f"{_pct(pick['share_then'])} a {_pct(pick['share_now'])} de lo que {'le' if them else 'nos'} falta de semana.")
    title = title[0].upper() + title[1:]
    others = sorted((m for m in moves if m["chain"] == pick["chain"] and m["title_norm"] != pick["title_norm"]
                     and m["delta_pp"] * pick["delta_pp"] < 0), key=lambda m: -abs(m["delta_pp"]))[:2]
    body = (f"{'Esas funciones se fueron' if net < 0 else 'El espacio salió'} "
            + ("de " if net > 0 else "a ") + " y ".join(f"{_short(m['title'], 26)} ({_pp(m['delta_pp'])})" for m in others) + ". "
            if others else "")
    ours = next((m for m in moves if m["chain"] != pick["chain"] and m["title_norm"] == pick["title_norm"]), None)
    mine = [r for r in movies_by_chain(conn, d0, d1, limit=200, hours=hours, plaza=plaza) if r["title_norm"] == pick["title_norm"]]
    if them:
        us_share = mine[0]["share_cinemex"] if mine else 0
        body += (f"Nosotros le damos {_pct(us_share)} de nuestra parrilla" +
                 (f" ({_pp(ours['delta_pp'])} en el mismo lapso)." if ours else "."))
        action = (f"Decisión: ¿seguimos su lectura de la demanda o sostenemos {t}?" if net < 0 else
                  f"Decisión: ¿le damos más sala a {t} antes del fin de semana?")
    else:
        body += f"{THEM_NAME} no movió ese título en la misma medida." if not ours or abs(ours["delta_pp"]) < MOVE_MIN_PP else \
                f"{THEM_NAME} lo movió {_pp(ours['delta_pp'])} en el mismo lapso."
        action = "Decisión: confirmar con ocupación que el ajuste fue el correcto"
    support = [{"label": f"Antes {CHAIN_LABEL[pick['chain']]}", "value": _pct(pick["share_then"]), "cmx": not them},
               {"label": f"Ahora {CHAIN_LABEL[pick['chain']]}", "value": _pct(pick["share_now"]), "cmx": not them},
               {"label": "Δ", "value": _pp(pick["delta_pp"]), "cmx": not them}]
    if them and mine:
        support.append({"label": "Nuestra parrilla", "value": _pct(mine[0]["share_cinemex"]), "cmx": True})
    return {"topic": "movimientos", "title": title, "body": body.strip(), "action": action, "support": support,
            "strength": abs(pick["delta_pp"]) / MOVE_MIN_PP}


def _price_finding(conn, d0, d1, hours=None, plaza=None):
    """Quién es más caro en lo que de verdad programa: boleto promedio ponderado por formato y tipo de día."""
    ep = {r["chain"]: r for r in effective_ticket_price(conn, d0, d1, hours=hours, plaza=plaza, days=PRICE_SAMPLE_DAYS)}
    us, them = ep.get(US), ep.get(THEM)
    if not us or not them or not us["avg_price"] or not them["avg_price"]:
        return None
    if min(us["pct_priced"], them["pct_priced"]) < PRICE_MIN_PRICED:
        return None
    gap = 100.0 * (them["avg_price"] / us["avg_price"] - 1)
    if abs(gap) < PRICE_MIN_PCT:
        return None
    med = {(r["chain"], r["format_bucket"], r["day_type"]): r["median_price"]
           for r in prices(conn, days=PRICE_SAMPLE_DAYS, plaza=plaza) if r["cinemas"] >= PRICE_MIN_CINEMAS}
    cells = sorted(((mc / mu - 1, b, d, mu, mc) for (ch, b, d), mu in med.items() if ch == US
                    for mc in [med.get((THEM, b, d))] if mu and mc), key=lambda x: (-abs(x[0]), x[1], x[2]))
    if gap > 0:
        title = (f"Ir al cine con nosotros cuesta {gap:.0f} % menos: nuestro boleto promedio de la cartelera es "
                 f"${us['avg_price']:,.0f} frente a ${them['avg_price']:,.0f} en {THEM_NAME}.")
    else:
        title = (f"Somos {abs(gap):.0f} % más caros en lo que programamos: boleto promedio de ${us['avg_price']:,.0f} "
                 f"frente a ${them['avg_price']:,.0f} en {THEM_NAME}.")
    body = "El promedio pondera el precio de cada formato y tipo de día por las funciones que cada cadena programa en el periodo."
    support = [{"label": "Boleto prom. Cinemex", "value": f"${us['avg_price']:,.0f}", "cmx": True},
               {"label": f"Boleto prom. {THEM_NAME}", "value": f"${them['avg_price']:,.0f}", "cmx": False}]
    if cells:
        r, b, d, mu, mc = cells[0]
        where = f"{FORMAT_LABEL[b]}, {DAY_TYPE_LABEL[d].lower()}"
        body += f" La mayor diferencia está en {where}: ${mu:,.0f} nuestro frente a ${mc:,.0f} suyo."
        support.append({"label": f"{FORMAT_LABEL[b]} · {DAY_TYPE_LABEL[d].lower()}", "value": f"${mu:,.0f} vs ${mc:,.0f}", "cmx": mu <= mc})
        action = (f"Decisión: ¿hay margen para subir {where} sin perder la ventaja de precio?" if r > 0 else
                  f"Decisión: revisar {where}, donde cobramos más que {THEM_NAME}")
    else:
        action = "Decisión: revisar la política de precio frente a la suya"
    return {"topic": "precio", "title": title, "body": body, "action": action, "support": support,
            "strength": _STRUCTURAL_WEIGHT * abs(gap) / PRICE_MIN_PCT, "as_of": min(us["last_sampled"], them["last_sampled"])}


def _demand_finding(conn, d0, d1, hours=None, plaza=None):
    """Un título que en las salas de Cinépolis vende muy por encima (o por debajo) de lo normal para su horario,
    contra cuánta parrilla le damos. Solo con plaza: los planos se leen en las plazas de `AC_SEATS_PLAZAS`."""
    if plaza is None:
        return None
    occ = occupancy_by_title(conn, days=DEMAND_SAMPLE_DAYS, min_samples=DEMAND_MIN_SAMPLES, plaza=plaza)
    movies = {m["title_norm"]: m for m in movies_by_chain(conn, d0, d1, limit=200, hours=hours, plaza=plaza)}
    best = None
    for o in occ:
        m = movies.get(o["title_norm"])
        if not m or o["demand_index"] is None:
            continue
        hot = (o["demand_index"] >= 1 + DEMAND_MIN_DEV and m["share_cinepolis"] >= DEMAND_MIN_SHARE
               and m["share_cinemex"] <= m["share_cinepolis"])
        cold = (o["demand_index"] <= 1 - DEMAND_MIN_DEV and m["share_cinemex"] >= TITLE_MIN_SHARE
                and m["share_cinemex"] > m["share_cinepolis"])
        score = abs(o["demand_index"] - 1) / DEMAND_MIN_DEV
        if (hot or cold) and (not best or score > best[0]):
            best = (score, o, m, hot)
    if not best:
        return None
    score, o, m, hot = best
    t = _short(o["title"])
    dev = abs(o["demand_index"] - 1) * 100
    if hot:
        title = (f"{t} vende en {THEM_NAME} {dev:.0f} % más de lo normal para su horario, y le damos "
                 + ("cero funciones." if not m["shows_cinemex"] else f"menos parrilla que ellos ({_pct(m['share_cinemex'])} frente a {_pct(m['share_cinepolis'])})."))
        action = f"Decisión: ¿abrir más funciones de {t} esta semana?"
    else:
        title = (f"{t} vende en {THEM_NAME} {dev:.0f} % menos de lo normal para su horario, y le damos más parrilla que "
                 f"ellos ({_pct(m['share_cinemex'])} frente a {_pct(m['share_cinepolis'])}).")
        action = f"Decisión: ¿mover funciones de {t} a un título con más demanda?"
    body = (f"Medido en {o['samples']:,} planos de sus funciones ya empezadas en los últimos {DEMAND_SAMPLE_DAYS} días: "
            f"{o['sold_pct']:.1f} % de butacas vendidas frente a {o['expected_pct']:.1f} % esperado por franja y tipo de día. "
            f"Es su sala, no la nuestra: nuestra ocupación entra cuando lleguen tus datos.")
    return {"topic": "demanda", "title": title, "body": body, "action": action, "strength": score, "as_of": o["last_sampled"],
            "support": [{"label": f"Vendido {THEM_NAME}", "value": f"{o['sold_pct']:.1f} %", "cmx": False},
                        {"label": "Esperado por horario", "value": f"{o['expected_pct']:.1f} %", "cmx": False},
                        {"label": "Parrilla Cinemex", "value": _pct(m["share_cinemex"]), "cmx": True},
                        {"label": f"Parrilla {THEM_NAME}", "value": _pct(m["share_cinepolis"]), "cmx": False}]}


def _presale_finding(conn, plaza=None):
    """La preventa nuestra que se despega: por ritmo (puntos de aforo vendidos al día) si hay dos lecturas, si no por
    el % del aforo que ya lleva vendido. No depende del periodo: la preventa es de funciones futuras."""
    ranking = [r for r in presale_ranking(conn, plaza=plaza) if r["shows"] >= PRESALE_MIN_SHOWS]
    paced = [r for r in ranking if r["pace_pct_day"] is not None and r["paced_shows"] >= PRESALE_MIN_SHOWS]
    key = "pace_pct_day" if len(paced) >= 2 else "sold_pct"
    pool = sorted(paced if len(paced) >= 2 else ranking, key=lambda r: -r[key])
    if len(pool) < 2 or pool[0][key] <= 0:
        return None
    first, second = pool[0], pool[1]
    ratio = first[key] / second[key] if second[key] > 0 else float("inf")
    if ratio < PRESALE_MIN_RATIO:
        return None
    t = _short(first["title"])
    when = (f"a {first['days_to_release']} días de su estreno" if first["days_to_release"] is not None else "en preventa")
    fmt = (lambda v: f"{v:.1f} pts/día") if key == "pace_pct_day" else (lambda v: f"{v:.0f} %")
    lead = ("más del triple" if ratio >= 3 else "más del doble") + f" que {_short(second['title'], 28)}"
    title = (f"{t} es la preventa que más rápido se vende: {first[key]:.1f} puntos de su aforo al día, {lead}."
             if key == "pace_pct_day" else
             f"{t} es la preventa más vendida: lleva {first[key]:.0f} % de su aforo, {lead}.")
    body = (f"Lleva {first['sold_pct']:.0f} % de las butacas vendidas en un panel de {first['shows']} funciones, {when}. "
            + ("" if key == "pace_pct_day" else "Con una sola lectura del panel el ritmo diario aún no se puede medir. "))
    return {"topic": "preventa", "title": title, "body": body.strip(),
            "action": f"Decisión: ¿abrir más funciones o salas grandes de {t} para el estreno?",
            "strength": min(ratio, 10.0) / PRESALE_MIN_RATIO, "as_of": first["last_sampled"],
            "support": [{"label": f"{_short(first['title'], 22)}", "value": fmt(first[key]), "cmx": True},
                        {"label": f"{_short(second['title'], 22)}", "value": fmt(second[key]), "cmx": False},
                        {"label": "Vendido del panel", "value": f"{first['sold_pct']:.0f} %", "cmx": True},
                        {"label": "Funciones leídas", "value": f"{first['shows']}", "cmx": False}]}


def _presale_gap_finding(conn, plaza=None):
    """El título en preventa en ambas cadenas donde una lleva vendido mucho más de su aforo que la otra."""
    shared = [r for r in presale_compare(conn, plaza=plaza)
              if r["gap_pp"] is not None and min(r["shows_cinemex"], r["shows_cinepolis"]) >= PRESALE_MIN_SHOWS]
    if not shared:
        return None
    r = max(shared, key=lambda x: (abs(x["gap_pp"]), x["title"]))
    if abs(r["gap_pp"]) < PRESALE_GAP_MIN_PP:
        return None
    t = _short(r["title"])
    us, them = r["sold_pct_cinemex"], r["sold_pct_cinepolis"]
    if r["gap_pp"] < 0:
        title = f"En la preventa de {t}, {THEM_NAME} va adelante: lleva {them:.0f} % de su aforo vendido y nosotros {us:.0f} %."
        action = f"Decisión: ¿reforzar la venta anticipada de {t} (difusión, salas, horarios) antes del estreno?"
    else:
        title = f"En la preventa de {t} vamos adelante: llevamos {us:.0f} % de nuestro aforo vendido y {THEM_NAME} {them:.0f} %."
        action = f"Decisión: ¿abrir más funciones de {t} mientras la demanda se inclina hacia nosotros?"
    body = (f"Medido con el plano de {r['shows_cinemex']} funciones nuestras y {r['shows_cinepolis']} suyas en preventa, en % del "
            f"aforo para que el tamaño de sala no pese.")
    return {"topic": "preventa_brecha", "title": title, "body": body, "action": action,
            "strength": abs(r["gap_pp"]) / PRESALE_GAP_MIN_PP, "as_of": None,
            "support": [{"label": "Vendido Cinemex", "value": f"{us:.0f} %", "cmx": True},
                        {"label": f"Vendido {THEM_NAME}", "value": f"{them:.0f} %", "cmx": False},
                        {"label": "Δ", "value": _pp(r["gap_pp"]), "cmx": r["gap_pp"] > 0},
                        {"label": "Estreno", "value": date_es(r["release_date"], with_year=False) if r["release_date"] else "—", "cmx": False}]}


def _presale_exclusive_finding(conn, plaza=None):
    """Preventas de Cinépolis de títulos que no exhibimos y que ya venden buena parte de su aforo."""
    theirs = [r for r in presale_compare(conn, plaza=plaza)
              if r["status"] == "exclusiva_cinepolis" and r["shows_cinepolis"] >= PRESALE_MIN_SHOWS]
    hot = sorted((r for r in theirs if r["sold_pct_cinepolis"] >= PRESALE_EXCLUSIVE_MIN_PCT),
                 key=lambda r: (-r["sold_pct_cinepolis"], r["title"]))
    if not hot:
        return None
    first = hot[0]
    t = _short(first["title"])
    title = (f"{THEM_NAME} tiene en preventa {len(theirs)} títulos que no exhibimos, y {t} ya lleva "
             f"{first['sold_pct_cinepolis']:.0f} % de su aforo vendido.")
    body = ("Otros que ya venden: " + ", ".join(f"{_short(r['title'], 26)} ({r['sold_pct_cinepolis']:.0f} %)" for r in hot[1:3]) + "."
            if len(hot) > 1 else f"Es el único de sus exclusivas en preventa que pasa de {PRESALE_EXCLUSIVE_MIN_PCT:.0f} %.")
    when = date_es(first["release_date"], with_year=False) if first["release_date"] else None
    return {"topic": "preventa_exclusiva", "title": title, "body": body,
            "action": f"Decisión: ¿buscar {t} para nuestra cartelera o contraprogramar {'el ' + when if when else 'su estreno'}?",
            "strength": first["sold_pct_cinepolis"] / PRESALE_EXCLUSIVE_MIN_PCT, "as_of": None,
            "support": [{"label": _short(r["title"], 22), "value": f"{r['sold_pct_cinepolis']:.0f} %", "cmx": False} for r in hot[:3]]
                       + [{"label": f"Exclusivas de {THEM_NAME}", "value": f"{len(theirs)}", "cmx": False}]}


def findings(conn, d0=None, d1=None, top=3, hours=None, plaza=None):
    """Los `top` hallazgos más fuertes (`strength` = brecha / umbral). Cada regla solo entra si
    cruza su umbral y, si depende de un muestreo, si el dato está vigente: movimientos del competidor, demanda por
    título (ocupación de Cinépolis), nuestra preventa que se despega, brecha de preventa en un
    mismo título, preventa exclusiva de Cinépolis que ya vende, título por butacas, concentración, dulcería, precio del boleto, franjas, formato y
    exclusivas; un empate conserva ese orden. Precio y formato pesan la mitad: cambian poco de semana a semana. `plaza` acota la
    cartelera; la dulcería a domicilio no depende de la plaza (Rappi y DiDi se leen en CDMX)."""
    d0 = d0 or today()
    d1 = d1 or d0
    kp = {r["chain"]: r for r in kpis(conn, d0, d1, hours=hours, plaza=plaza)}
    if US not in kp or THEM not in kp:
        return []
    movies = movies_by_chain(conn, d0, d1, limit=200, hours=hours, plaza=plaza)
    out = []
    for fn in (lambda: _moves_finding(conn, d0, d1, hours=hours, plaza=plaza),
               lambda: _demand_finding(conn, d0, d1, hours=hours, plaza=plaza),
               lambda: _presale_finding(conn, plaza=plaza),
               lambda: _presale_gap_finding(conn, plaza=plaza),
               lambda: _presale_exclusive_finding(conn, plaza=plaza),
               lambda: _title_finding(conn, d0, d1, hours=hours, plaza=plaza),
               lambda: _concentration_finding(conn, d0, d1, movies, hours=hours, plaza=plaza),
               lambda: _concession_finding(conn),
               lambda: _price_finding(conn, d0, d1, hours=hours, plaza=plaza),
               lambda: _slot_finding(conn, d0, d1, hours=hours, plaza=plaza),
               lambda: _format_finding(conn, d0, d1, kp, hours=hours, plaza=plaza),
               lambda: _exclusive_finding(movies)):
        f = fn()
        if f:
            f.setdefault("as_of", None)
            out.append(f)
    return sorted(out, key=lambda f: -f["strength"])[:top]


def conclusions(conn, d0=None, d1=None, shown=8, total=15, hours=None, plaza=None):
    """Frase de apertura de cada sección de evidencia (Capa 2)."""
    d0 = d0 or today()
    d1 = d1 or d0
    out = {}
    kp = {r["chain"]: r for r in kpis(conn, d0, d1, hours=hours, plaza=plaza)}
    us, them = kp.get(US), kp.get(THEM)
    if not us or not them:
        return out

    # Resumen general: volumen total y cuánto concentra el Top del reporte del cliente.
    summary = general_summary(conn, d0, d1, hours=hours, plaza=plaza)
    titles = [r for r in summary if r["kind"] == "title"]
    tot = summary[-1]
    top_us, top_them = sum(r["share_cinemex"] for r in titles), sum(r["share_cinepolis"] for r in titles)
    ratio = f"{tot['ratio']:.2f}" if tot["ratio"] else "—"
    out["resumen"] = (f"Publicamos {tot['shows_cinemex']:,} funciones frente a {tot['shows_cinepolis']:,} de {THEM_NAME} "
                      f"({ratio} funciones suyas por cada una nuestra); las {len(titles)} películas con más funciones concentran "
                      f"{_pct(top_us)} de nuestra parrilla y {_pct(top_them)} de la suya.")

    # Películas: sobre-indexamos / ellos apuestan más / exclusivas, sobre las `total` con más funciones.
    top_movies = movies_by_chain(conn, d0, d1, limit=total, hours=hours, plaza=plaza)
    shared = [m for m in top_movies if m["shows_cinemex"] and m["shows_cinepolis"]]
    more = sorted([m for m in shared if m["gap_pp"] >= 1], key=lambda m: -m["gap_pp"])[:2]
    less = sorted([m for m in shared if m["gap_pp"] <= -1], key=lambda m: m["gap_pp"])[:2]
    only_us = [m for m in top_movies if not m["shows_cinepolis"]]
    only_them = [m for m in top_movies if not m["shows_cinemex"]]
    parts = []
    if more:
        parts.append("Sobre-indexamos en " + " y ".join(f"{_short(m['title'], 28)} ({_pp(m['gap_pp'])})" for m in more))
    if less:
        doubles = all(m["share_cinepolis"] >= 2 * m["share_cinemex"] for m in less)
        parts.append(f"{THEM_NAME} {'nos dobla' if doubles else 'apuesta más'} en " +
                     " y ".join(f"{_short(m['title'], 28)} ({_pp(m['gap_pp'])})" for m in less))
    if only_us or only_them:
        ex = []
        if only_us:
            ex.append(f"{len(only_us)} exclusiva{'s' if len(only_us) != 1 else ''} nuestra{'s' if len(only_us) != 1 else ''}")
        if only_them:
            ex.append(f"{len(only_them)} de {THEM_NAME}")
        parts.append("entre los títulos más programados hay " + " y ".join(ex))
    out["peliculas"] = "; ".join(parts) + "." if parts else f"Repartimos la parrilla casi igual que {THEM_NAME} entre los títulos principales."
    out["peliculas_note"] = f"Mostrando las {shown} con mayor diferencia; el resto no mueve decisiones."

    # Franjas: dónde ganamos y dónde perdemos.
    slots = {r["chain"]: r for r in showtimes_by_slot(conn, d0, d1, hours=hours, plaza=plaza)}
    su, st_ = slots[US], slots[THEM]
    h0, h1 = hours or FULL_DAY
    gaps = {k: 100.0 * su[k] / su["total"] - 100.0 * st_[k] / st_["total"] for k, lo, hi, _ in SLOTS
            if lo >= h0 and hi <= h1 and (su[k] or st_[k])}
    win = sorted([k for k in gaps if gaps[k] >= 0.5], key=lambda k: -gaps[k])
    lose = sorted([k for k in gaps if gaps[k] <= -0.5], key=lambda k: gaps[k])
    txt = []
    if win:
        txt.append("Ganamos " + " y ".join(_slot_phrase(k) for k in win[:2]))
    if lose:
        k = lose[0]
        txt.append(f"perdemos {_slot_phrase(k)}, donde {THEM_NAME} pone {abs(gaps[k]):.1f} pp más" +
                   (f", y también {_slot_phrase(lose[1])}" if len(lose) > 1 else ""))
    out["franjas"] = ("; ".join(txt) + "." if txt else f"La distribución por franja es prácticamente la misma que la de {THEM_NAME}.")
    out["franjas"] = out["franjas"][0].upper() + out["franjas"][1:]

    # Formatos e idioma.
    mx = {(r["dimension"], r["chain"], r["bucket"]): r["share"] for r in mix(conn, d0, d1, hours=hours, plaza=plaza)}
    fg = [(mx.get(("format", US, b), 0) - mx.get(("format", THEM, b), 0), b) for b in FORMAT_LABEL if b != "traditional"]
    g, b = max(fg, key=lambda x: abs(x[0]))
    u, t = mx.get(("format", US, b), 0), mx.get(("format", THEM, b), 0)
    if abs(g) >= 2:
        fmt = (f"Nuestra diferencia estructural es {FORMAT_LABEL[b]}: {_pct(u)} de nuestras funciones frente a {_pct(t)} en {THEM_NAME}."
               if g > 0 else
               f"{THEM_NAME} pone más en {FORMAT_LABEL[b]}: {_pct(t)} de sus funciones frente a {_pct(u)} nuestras.")
    else:
        fmt = f"El mix de formato es casi el mismo que el de {THEM_NAME}."
    ds = us["pct_subtitled"] - them["pct_subtitled"]
    if ds <= -1:
        fmt += f" Ellos subtitulan más ({them['pct_subtitled']:.0f} % vs {us['pct_subtitled']:.0f} %)."
    elif ds >= 1:
        fmt += f" Nosotros subtitulamos más ({us['pct_subtitled']:.0f} % vs {them['pct_subtitled']:.0f} %)."
    out["formatos"] = fmt

    # Preventa: cuántos títulos tenemos en preventa y cuál se vende más.
    ranking = [r for r in presale_ranking(conn, plaza=plaza) if r["shows"] >= PRESALE_MIN_SHOWS]
    compare = presale_compare(conn, plaza=plaza)
    shared = [r for r in compare if r["gap_pp"] is not None and min(r["shows_cinemex"], r["shows_cinepolis"]) >= PRESALE_MIN_SHOWS]
    only_them = [r for r in compare if r["status"] == "exclusiva_cinepolis" and r["shows_cinepolis"] >= PRESALE_MIN_SHOWS]
    only_us = [r for r in compare if r["status"] == "exclusiva_cinemex" and r["shows_cinemex"] >= PRESALE_MIN_SHOWS]
    if ranking:
        top = ranking[0]
        out["preventa"] = (f"Tenemos {len(ranking)} títulos en preventa con panel suficiente; {_short(top['title'], 50)} "
                           + (f"vende {top['pace_pct_day']:.1f} puntos de su aforo al día y lleva {top['sold_pct']:.0f} % vendido."
                              if top["pace_pct_day"] is not None else f"es el que más lleva vendido: {top['sold_pct']:.0f} % del aforo de su panel."))
        if shared:
            ahead = sum(r["gap_pp"] > 0 for r in shared)
            out["preventa"] += (f" En los {len(shared)} títulos que ambas cadenas tienen en preventa, vamos adelante en {ahead}"
                                f" y {THEM_NAME} en {len(shared) - ahead}.")
        if only_them or only_us:
            out["preventa"] += (f" Exclusivas en preventa: nosotros {len(only_us)} y {THEM_NAME} {len(only_them)}"
                                + (f", la más vendida {_short(only_them[0]['title'], 30)} ({only_them[0]['sold_pct_cinepolis']:.0f} %)."
                                   if only_them else "."))

    # Dulcería: brecha a domicilio (misma plataforma) y modelo de precio en sala.
    gap, cmp_, as_of = _concession_gap(conn)
    basket = {r["product_name"]: r for r in concession_basket(conn)}
    pop = basket.get("Palomitas")
    if gap is not None:
        who = (f"{THEM_NAME} cobra {gap:.0f} % más que nosotros" if gap > 0 else f"cobramos {abs(gap):.0f} % más que {THEM_NAME}")
        when = "" if _is_fresh(as_of, CONCESSION_MAX_AGE_DAYS) else f" con los precios del {date_es(_local_date(as_of), with_year=False)}, la última lectura,"
        out["dulceria"] = (f"En la dulcería a domicilio{when} {who} en la canasta comparable ({len(cmp_)} tipos de producto)"
                           + (f"; en sala, {THEM_NAME} fija precio por complejo (palomitas de ${pop['min_price']:,.0f} a "
                              f"${pop['max_price']:,.0f}) y nosotros una lista única." if pop else "."))
    elif pop:
        out["dulceria"] = (f"{THEM_NAME} fija el precio de dulcería por complejo: palomitas de ${pop['min_price']:,.0f} a "
                           f"${pop['max_price']:,.0f} en {int(pop['distinct_prices'])} niveles. Nuestra lista llegará con tus datos.")
    return out
