"""Capa 1 y conclusiones de Capa 2 del dashboard: hallazgos redactados como decisión.

Cada hallazgo sale de las mismas consultas que el resto del dashboard y se redacta solo si cruza un
umbral que lo hace relevante para una decisión de programación esta semana. Nunca hay cifras fijas
aquí: si el dato no existe, el hallazgo no aparece. Hablamos en primera persona como Cinemex.

`findings()` devuelve hasta `top` dicts {title, body, action, support: [{label, value, cmx}]}.
`conclusions()` devuelve {peliculas, peliculas_note, franjas, formatos}: la frase que abre cada
sección de evidencia."""
from .concessions import concession_basket
from .delivery import delivery_compare, delivery_summary
from .labels import CHAIN_LABEL, FORMAT_LABEL, FULL_DAY, SLOT_SHORT, SLOTS, THEM, US, WEEKDAY_LABEL
from .queries import concentration, heatmap_day_slot, is_full_day, kpis, mix, movies_by_chain, showtimes_by_slot, today
from .seats import offered_by_title
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


def _title_finding(conn, d0, d1, hours=None):
    """¿Dónde la apuesta por sala (butacas) cuenta otra historia que la apuesta por funciones?"""
    movies = movies_by_chain(conn, d0, d1, limit=60, hours=hours)
    seats = {c: {r["title_norm"]: r for r in offered_by_title(conn, d0, d1, limit=60, chain=c, hours=hours)} for c in (US, THEM)}
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
    return {"topic": "titulo", "title": title, "body": body, "action": action, "support": support[:4] + support[4:6]}


def _concentration_finding(conn, d0, d1, movies, hours=None):
    cc = {r["chain"]: r for r in concentration(conn, d0, d1, hours=hours)}
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
    return {"topic": "concentracion", "title": title, "body": body, "action": action, "support": [
        {"label": "Top 3 Cinemex", "value": _pct(cu["top3_pct"]), "cmx": True},
        {"label": f"Top 3 {THEM_NAME}", "value": _pct(ct["top3_pct"]), "cmx": False},
        {"label": "Títulos Cinemex", "value": f"{cu['titles']}", "cmx": True},
        {"label": f"Títulos {THEM_NAME}", "value": f"{ct['titles']}", "cmx": False},
    ]}


def _slot_finding(conn, d0, d1, hours=None):
    if not is_full_day(hours):
        return None   # con la franja recortada, la "franja ganadora" pierde el sentido comparativo
    slots = {r["chain"]: r for r in showtimes_by_slot(conn, d0, d1)}
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
    hm = heatmap_day_slot(conn, d0, d1)
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
    return {"topic": "franjas", "title": title, "body": body, "action": action, "support": support[:4]}


def _format_finding(conn, d0, d1, kp, hours=None):
    mx = {(r["dimension"], r["chain"], r["bucket"]): r["share"] for r in mix(conn, d0, d1, hours=hours)}
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
    return {"topic": "formato", "title": title, "body": body, "action": action, "support": [
        {"label": f"{FORMAT_LABEL[b]} Cinemex", "value": _pct(u), "cmx": True},
        {"label": f"{FORMAT_LABEL[b]} {THEM_NAME}", "value": _pct(t), "cmx": False},
        {"label": "Subtituladas Cinemex", "value": _pct(us["pct_subtitled"]) if us else "—", "cmx": True},
        {"label": f"Subtituladas {THEM_NAME}", "value": _pct(them["pct_subtitled"]) if them else "—", "cmx": False},
    ]}


def _concession_gap(conn):
    """Brecha mediana (%) Cinépolis vs Cinemex en las cubetas comparables de dulcería a domicilio, y las cubetas."""
    cmp_ = [r for r in delivery_compare(conn) if r["delta_pct"] is not None]
    if not cmp_:
        return None, []
    gaps = sorted(r["delta_pct"] for r in cmp_)
    return gaps[len(gaps) // 2], cmp_


def _concession_finding(conn):
    gap, cmp_ = _concession_gap(conn)
    if gap is None or abs(gap) < CONCESSION_MIN_PCT:
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
    return {"topic": "dulceria", "title": title, "body": body, "action": action, "support": support[:5]}


def _exclusive_finding(movies):
    only_them = [m for m in movies if not m["shows_cinemex"] and m["shows_cinepolis"] >= EXCLUSIVE_MIN_SHOWS]
    only_us = [m for m in movies if not m["shows_cinepolis"] and m["shows_cinemex"] >= EXCLUSIVE_MIN_SHOWS]
    if len(only_them) < EXCLUSIVE_MIN_TITLES:
        return None
    names = ", ".join(_short(m["title"], 26) for m in only_them[:3])
    title = f"{THEM_NAME} exhibe {len(only_them)} títulos que no tenemos; el mayor se lleva {_pct(only_them[0]['share_cinepolis'])} de su parrilla."
    body = f"{names}" + (f" y {len(only_them) - 3} más." if len(only_them) > 3 else ".") + \
           (f" Nosotros tenemos {len(only_us)} exclusivas." if only_us else "")
    return {"topic": "exclusivas", "title": title, "body": body,
            "action": "Decisión: ¿alguna exclusiva de Cinépolis merece sala esta semana?",
            "support": [{"label": f"Solo {THEM_NAME}", "value": f"{len(only_them)} títulos", "cmx": False},
                        {"label": "Solo Cinemex", "value": f"{len(only_us)} títulos", "cmx": True}] +
                       [{"label": _short(m["title"], 22), "value": _pct(m["share_cinepolis"]), "cmx": False} for m in only_them[:2]]}


def findings(conn, d0=None, d1=None, top=3, hours=None):
    """Hasta `top` hallazgos, en orden de prioridad: título por butacas, concentración, dulcería (información de
    valor directo para el cliente), franjas, formato, exclusivas. Cada uno solo entra si cruza su umbral."""
    d0 = d0 or today()
    d1 = d1 or d0
    kp = {r["chain"]: r for r in kpis(conn, d0, d1, hours=hours)}
    if US not in kp or THEM not in kp:
        return []
    movies = movies_by_chain(conn, d0, d1, limit=200, hours=hours)
    out = []
    for fn in (lambda: _title_finding(conn, d0, d1, hours=hours),
               lambda: _concentration_finding(conn, d0, d1, movies, hours=hours),
               lambda: _concession_finding(conn),
               lambda: _slot_finding(conn, d0, d1, hours=hours),
               lambda: _format_finding(conn, d0, d1, kp, hours=hours),
               lambda: _exclusive_finding(movies)):
        f = fn()
        if f:
            out.append(f)
        if len(out) >= top:
            break
    return out


def conclusions(conn, d0=None, d1=None, shown=8, total=15, hours=None):
    """Frase de apertura de cada sección de evidencia (Capa 2)."""
    d0 = d0 or today()
    d1 = d1 or d0
    out = {}
    kp = {r["chain"]: r for r in kpis(conn, d0, d1, hours=hours)}
    us, them = kp.get(US), kp.get(THEM)
    if not us or not them:
        return out

    # Resumen general: volumen total y cuánto concentra el Top del reporte del cliente.
    summary = general_summary(conn, d0, d1, hours=hours)
    titles = [r for r in summary if r["kind"] == "title"]
    tot = summary[-1]
    top_us, top_them = sum(r["share_cinemex"] for r in titles), sum(r["share_cinepolis"] for r in titles)
    ratio = f"{tot['ratio']:.2f}" if tot["ratio"] else "—"
    out["resumen"] = (f"Publicamos {tot['shows_cinemex']:,} funciones frente a {tot['shows_cinepolis']:,} de {THEM_NAME} "
                      f"({ratio} funciones suyas por cada una nuestra); las {len(titles)} películas con más funciones concentran "
                      f"{_pct(top_us)} de nuestra parrilla y {_pct(top_them)} de la suya.")

    # Películas: sobre-indexamos / ellos apuestan más / exclusivas, sobre las `total` con más funciones.
    top_movies = movies_by_chain(conn, d0, d1, limit=total, hours=hours)
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
    slots = {r["chain"]: r for r in showtimes_by_slot(conn, d0, d1, hours=hours)}
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
    mx = {(r["dimension"], r["chain"], r["bucket"]): r["share"] for r in mix(conn, d0, d1, hours=hours)}
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

    # Dulcería: brecha a domicilio (misma plataforma) y modelo de precio en sala.
    gap, cmp_ = _concession_gap(conn)
    basket = {r["product_name"]: r for r in concession_basket(conn)}
    pop = basket.get("Palomitas")
    if gap is not None:
        who = (f"{THEM_NAME} cobra {gap:.0f} % más que nosotros" if gap > 0 else f"cobramos {abs(gap):.0f} % más que {THEM_NAME}")
        out["dulceria"] = (f"En la dulcería a domicilio {who} en la canasta comparable ({len(cmp_)} tipos de producto)"
                           + (f"; en sala, {THEM_NAME} fija precio por complejo (palomitas de ${pop['min_price']:,.0f} a "
                              f"${pop['max_price']:,.0f}) y nosotros una lista única." if pop else "."))
    elif pop:
        out["dulceria"] = (f"{THEM_NAME} fija el precio de dulcería por complejo: palomitas de ${pop['min_price']:,.0f} a "
                           f"${pop['max_price']:,.0f} en {int(pop['distinct_prices'])} niveles. Nuestra lista llegará con tus datos.")
    return out
