"""Lectura ejecutiva: frases en español que explican qué dicen los números de la ventana.
Hablamos en primera persona como Cinemex (labels.US) y comparamos siempre por share (% de la
programación de cada cadena), porque las cadenas no tienen el mismo número de cines ni salas.

Cada frase lleva `topic`, para que el dashboard la coloque junto a la gráfica que la sustenta."""
from .labels import CHAIN_LABEL, FORMAT_LABEL, KIND_LABEL, KIND_PLURAL, SLOTS, THEM, US, range_es, time_12
from .queries import _window, concentration, events_by_kind, kpis, mix, movies_by_chain, showtimes_by_slot, today

THEM_NAME = CHAIN_LABEL[THEM]


def _pct(part, whole):
    return round(100.0 * part / whole) if whole else 0


def _fmt(x, nd=1):
    return f"{x:,.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"


def _lc(label):
    return label[0].lower() + label[1:]


def headlines(conn, d0=None, d1=None, min_shows=20, top=3):
    """Lista de dicts {topic, text}. Topics: volumen, franjas, peliculas, exclusivas, idioma,
    formato, concentracion, cambios."""
    d0 = d0 or today()
    d1 = d1 or d0
    _, _, from_hhmm = _window(d0, d1)
    out = []

    kp = {r["chain"]: r for r in kpis(conn, d0, d1)}
    us, them = kp.get(US), kp.get(THEM)
    if from_hhmm and d0 == d1:
        when = f"hoy a partir de las {time_12(from_hhmm)}"
    elif from_hhmm:
        when = f"de hoy (desde las {time_12(from_hhmm)}) al {range_es(d1, d1)}"
    else:
        when = range_es(d0, d1)
    if not us or not them:
        out.append({"topic": "volumen", "text": f"No hay cartelera de ambas cadenas para {when}."})
        return out

    # 1. Volumen
    diff = us["shows_per_cinema"] - them["shows_per_cinema"]
    per_day = "" if us["days"] == 1 else " al día"
    text = (f"Tenemos {_fmt(us['shows'])} funciones en {us['cinemas']} cines {when}, "
            f"{_fmt(us['shows_per_cinema'])} por cine{per_day}. {THEM_NAME} tiene {_fmt(them['shows'])} en "
            f"{them['cinemas']} cines, {_fmt(them['shows_per_cinema'])} por cine{per_day}")
    if abs(diff) >= 0.5:
        n = _fmt(abs(diff))
        text += f": programamos {n} {'función' if n == '1' else 'funciones'} {'más' if diff > 0 else 'menos'} por cine{per_day}."
    else:
        text += ": la oferta por cine es prácticamente la misma."
    out.append({"topic": "volumen", "text": text})

    # 2. Horario prime y franjas
    if us["weekend_shows"] and them["weekend_shows"]:
        d = us["pct_prime"] - them["pct_prime"]
        out.append({"topic": "prime", "text":
                    f"El {round(us['pct_prime'])}% de nuestras funciones cae en horario prime (viernes a domingo "
                    f"desde las 6:00 P.M.), frente al {round(them['pct_prime'])}% de {THEM_NAME}: "
                    + (f"{abs(d):.1f} puntos {'más' if d > 0 else 'menos'} de nuestra parrilla en el bloque donde vive la taquilla."
                       if abs(d) >= 1 else "la misma apuesta por el bloque donde vive la taquilla.")})
    slots = {r["chain"]: r for r in showtimes_by_slot(conn, d0, d1)}
    su, st = slots[US], slots[THEM]
    peak_us = max(SLOTS, key=lambda s: su[s[0]])
    peak_them = max(SLOTS, key=lambda s: st[s[0]])
    text = (f"Nuestra franja más cargada es de {_lc(peak_us[3])}, con el {_pct(su[peak_us[0]], su['total'])}% "
            f"de nuestras funciones")
    if peak_them[0] == peak_us[0]:
        text += f"; {THEM_NAME} también concentra ahí el {_pct(st[peak_them[0]], st['total'])}% de las suyas."
    else:
        text += f"; {THEM_NAME} concentra la suya de {_lc(peak_them[3])} ({_pct(st[peak_them[0]], st['total'])}%)."
    gaps = [(100.0 * su[k] / su["total"] - 100.0 * st[k] / st["total"], label) for k, _, _, label in SLOTS]
    g, label = max(gaps, key=lambda x: abs(x[0]))
    if abs(g) >= 2:
        text += (f" La mayor diferencia está de {_lc(label)}: {'nosotros' if g > 0 else THEM_NAME} "
                 f"{'ponemos' if g > 0 else 'pone'} ahí {abs(g):.1f} puntos más de {'nuestra' if g > 0 else 'su'} parrilla.")
    out.append({"topic": "franjas", "text": text})

    # 3. Películas
    movies = [m for m in movies_by_chain(conn, d0, d1, limit=200) if m["shows_total"] >= min_shows]
    shared = [m for m in movies if m["shows_cinemex"] and m["shows_cinepolis"]]
    more = sorted([m for m in shared if m["gap_pp"] >= 2], key=lambda m: -m["gap_pp"])[:top]
    less = sorted([m for m in shared if m["gap_pp"] <= -2], key=lambda m: m["gap_pp"])[:top]

    def movie_phrase(m):
        return (f"{m['title'].strip()} ({round(m['share_cinemex'])}% de nuestras funciones frente a "
                f"{round(m['share_cinepolis'])}% en {THEM_NAME})")

    if shared:
        lead = max(shared, key=lambda m: m["shows_total"])
        out.append({"topic": "peliculas", "text":
                    f"La película con más funciones en la plaza es {lead['title'].strip()}: se lleva el "
                    f"{round(lead['share_cinemex'])}% de nuestra programación ({_fmt(lead['shows_cinemex'])} funciones) y el "
                    f"{round(lead['share_cinepolis'])}% de la de {THEM_NAME} ({_fmt(lead['shows_cinepolis'])})."})
    if more:
        out.append({"topic": "peliculas", "text":
                    "Apostamos más fuerte que " + THEM_NAME + " en " + "; ".join(movie_phrase(m) for m in more) + "."})
    if less:
        out.append({"topic": "peliculas", "text":
                    THEM_NAME + " apuesta más fuerte que nosotros en " + "; ".join(movie_phrase(m) for m in less) + "."})
    only_them = [m for m in movies if not m["shows_cinemex"]]
    only_us = [m for m in movies if not m["shows_cinepolis"]]
    for lst, tmpl in ((only_them, "{them} exhibe {n} título{s} que nosotros no tenemos: {names}{extra}."),
                      (only_us, "Exhibimos {n} título{s} que {them} no tiene: {names}{extra}.")):
        if lst:
            n = len(lst)
            out.append({"topic": "exclusivas", "text": tmpl.format(
                them=THEM_NAME, n=n, s="s" if n != 1 else "",
                names=", ".join(m["title"].strip() for m in lst[:top]),
                extra=f" y {n - top} más" if n > top else "")})

    # 4. Mix: idioma y formato
    out.append({"topic": "idioma", "text":
                f"El {round(us['pct_subtitled'])}% de nuestras funciones son subtituladas; en {THEM_NAME} es el "
                f"{round(them['pct_subtitled'])}%."})
    mx = {(r["dimension"], r["chain"], r["bucket"]): r["share"] for r in mix(conn, d0, d1)}
    fmt_gaps = [(mx.get(("format", US, b), 0) - mx.get(("format", THEM, b), 0), b) for b in FORMAT_LABEL]
    g, b = max(fmt_gaps, key=lambda x: abs(x[0]))
    if abs(g) >= 2:
        out.append({"topic": "formato", "text":
                    f"En formato la mayor diferencia es {FORMAT_LABEL[b]}: {round(mx.get(('format', US, b), 0))}% de "
                    f"nuestras funciones frente a {round(mx.get(('format', THEM, b), 0))}% en {THEM_NAME}."})

    # 5. Concentración
    cc = {r["chain"]: r for r in concentration(conn, d0, d1)}
    if US in cc and THEM in cc:
        cu, ct = cc[US], cc[THEM]
        who = "nosotros" if cu["top3_pct"] > ct["top3_pct"] else THEM_NAME
        out.append({"topic": "concentracion", "text":
                    f"Nuestras tres películas más programadas se llevan el {round(cu['top3_pct'])}% de la parrilla; "
                    f"en {THEM_NAME}, el {round(ct['top3_pct'])}%. {'Concentramos' if who == 'nosotros' else THEM_NAME + ' concentra'} "
                    f"más la apuesta. Títulos distintos por complejo: {_fmt(cu['titles_per_cinema'])} nosotros, "
                    f"{_fmt(ct['titles_per_cinema'])} {THEM_NAME}."})

    # 6. Cambios de las últimas 24 h
    ev = {(r["chain"], r["kind"]): r["n"] for r in events_by_kind(conn, 24) if r["kind"] != "availability"}
    parts = []
    for chain, who in ((THEM, THEM_NAME), (US, "nosotros")):
        bits = [f"{n} {(KIND_PLURAL if n != 1 else KIND_LABEL)[k].lower()}"
                for (c, k), n in sorted(ev.items(), key=lambda kv: -kv[1]) if c == chain]
        if bits:
            parts.append(f"{who}: " + ", ".join(bits))
    if parts:
        out.append({"topic": "cambios", "text": "Cambios en la cartelera publicada en las últimas 24 horas. " +
                    ". ".join(p[0].upper() + p[1:] for p in parts) + "."})
    else:
        out.append({"topic": "cambios", "text": "Sin cambios en la cartelera publicada en las últimas 24 horas."})
    return out
