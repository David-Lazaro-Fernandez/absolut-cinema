"""Página principal: la cartelera en tres capas (hallazgos → evidencia → apéndice) con los filtros de periodo y
franja horaria en la barra lateral. La dulcería vive en su propia página (views/dulceria.py)."""
from ui.common import *  # noqa: F401,F403

# --- barra lateral: periodo y alcance -------------------------------------------------------------------
today_s = analytics.today()
today_d = date.fromisoformat(today_s)
if not config.DB_PATH.exists():
    # Recién desplegado: el scraper aún no ha creado la base. Aviso claro en lugar del traceback.
    now_hm = datetime.now(TZ).strftime("%H:%M")
    nxt = next((hm for hm in config.SNAPSHOT_HOURS if hm > now_hm), config.SNAPSHOT_HOURS[0])
    md('<div class="enc"><h1>Cartelera CDMX: <span>Cinemex</span> frente a Cinépolis</h1></div>')
    st.info(f"Aún no hay datos: la base {config.DB_PATH} no existe. La cartelera se captura a las "
            f"{', '.join(time_12(hm) for hm in config.SNAPSHOT_HOURS)}; la siguiente captura es a las {time_12(nxt)} y tarda de 2 a 5 "
            "minutos. Para no esperar: `make snapshot` (o `systemctl start absolut-cinema-scraper.service` en el servidor), o copia "
            "`data/` desde la máquina donde ya corre. Esta página se refresca sola.")
    st.stop()
cov = load("coverage")
if cov.empty:
    st.info("La base existe pero todavía no tiene funciones capturadas. Revisa `data/logs/run.log`.")
    st.stop()
this_w0, this_w1 = analytics.cinema_week(today_s)
next_w0, next_w1 = analytics.cinema_week((date.fromisoformat(this_w1) + timedelta(days=1)).isoformat())
full_day = cov[(cov.date >= today_s) & (cov.date <= this_w1)].cinemex.max() or 1
next_cov = cov[(cov.date >= next_w0) & (cov.date <= next_w1)]
next_state = "" if next_cov.empty else (" · publicada parcialmente" if next_cov.cinemex.mean() < 0.6 * full_day else " · publicada")

periods = {
    "Hoy": (today_s, today_s),
    "Mañana": ((today_d + timedelta(days=1)).isoformat(),) * 2,
    f"Resto de la semana de cine (hasta el {date_es(this_w1, with_year=False)})": (today_s, this_w1),
    f"Semana de cine siguiente ({date_es(next_w0, with_year=False)} a {date_es(next_w1, with_year=False)}){next_state}": (next_w0, next_w1),
    "Elegir fechas": None,
}
st.sidebar.header("Periodo")
choice = st.sidebar.radio("Semana o día a analizar", list(periods), index=2, label_visibility="collapsed")
if periods[choice] is None:
    rng = st.sidebar.date_input("Del … al …", value=(today_d, date.fromisoformat(this_w1)),
                                min_value=today_d - timedelta(days=1), max_value=today_d + timedelta(days=35),
                                format="DD/MM/YYYY")
    d0, d1 = (rng[0].isoformat(), rng[-1].isoformat()) if isinstance(rng, tuple) and rng else (today_s, today_s)
else:
    d0, d1 = periods[choice]
includes_today = d0 <= today_s <= d1

# Franja horaria: filtra por la hora de inicio de la función y aplica a todo el tablero salvo al Resumen general,
# que muestra sus dos cortes lado a lado. Solo corta en los límites de las franjas, así ninguna queda partida.
st.sidebar.header("Franja horaria")
preset = st.sidebar.radio("Franja horaria", list(HOUR_PRESETS) + ["Rango libre"], index=0, label_visibility="collapsed", key="hours_preset")
if preset == "Rango libre":
    hours = st.sidebar.select_slider("Hora de inicio de la función", options=HOUR_MARKS, value=FULL_DAY, format_func=hour_mark,
                                     key="hours_range")
else:
    hours = HOUR_PRESETS[preset]
hours = tuple(hours)
full_day = analytics.is_full_day(hours)
if not full_day:
    st.sidebar.caption(f"Solo funciones que empiezan {hours_label(hours)}. Las participaciones se calculan dentro de esa franja.")

st.sidebar.header("Zona")
st.sidebar.selectbox("Alcance geográfico", ["Toda la ciudad"], disabled=True)
st.sidebar.caption("Zonas de choque y mercados cautivos se habilitan al emparejar los cines de ambas cadenas por distancia.")

st.sidebar.header("Cómo leer las cifras")
st.sidebar.markdown(
    "Todo se compara en **porcentaje de la programación de cada cadena** (share), no en totales: Cinemex tiene "
    "más cines que Cinépolis en la plaza. Las diferencias entre porcentajes van en **puntos porcentuales (pp)**."
    + (" Para hoy solo se cuentan funciones que aún no han empezado, en ambas cadenas." if includes_today else ""))
with st.sidebar.expander("Glosario"):
    st.markdown(
        "- **Función.** Una proyección de una película en una sala a una hora.\n"
        "- **Aforo.** Butacas vendibles de una sala; se mide una vez por sala en el plano de asientos.\n"
        "- **Butacas ofertadas.** Suma del aforo de la sala por cada función del periodo: el máximo de boletos "
        "que la cadena podría vender en esos días. Un cine con 10 salas de 150 butacas y 5 funciones por sala "
        "oferta 7,500 al día.\n"
        "- **Butacas ocupadas.** Boletos vendidos. En Cinépolis se leen del plano a una hora de la función; en "
        "Cinemex se estiman a partir de su semáforo de disponibilidad, calibrado con planos reales.\n"
        "- **Ocupación.** Butacas ocupadas entre butacas ofertadas.\n"
        "- **Share.** Parte de la programación de una cadena que se lleva una película, franja o formato.\n"
        "- **Puntos porcentuales (pp).** Diferencia entre dos porcentajes. De 18 % a 21 % son +3 pp.\n"
        "- **Semana de cine.** De jueves a miércoles; es lo que ambas cadenas publican completo.\n"
        "- **Horario prime.** Viernes a domingo de 6:00 P.M. en adelante.")
st.sidebar.caption(f"La cartelera se captura a las {', '.join(time_12(hm) for hm in config.SNAPSHOT_HOURS)} y los planos de "
                   f"asientos cada 15 minutos; esta página se refresca cada {TTL} segundos.")

# --- datos del encabezado ---------------------------------------------------------------------------------
health = load("snapshot_health", limit=12)
last_ok = health[health.ok == 1].groupby("chain").first()
# Una cadena está desactualizada si su intento más reciente falló o si su última captura buena tiene más de
# MAX_AGE_MIN de scraper.health (la cartelera se captura tres veces al día; el hueco nocturno normal es de 11 h).
# Fallos ya superados por una captura buena no avisan.
now_utc = datetime.now(ZoneInfo("UTC"))
stale = []
for chain, r in health.groupby("chain").first().iterrows():
    last_good = last_ok.loc[chain].taken_at if chain in last_ok.index else None
    age_min = (now_utc - datetime.fromisoformat(last_good)).total_seconds() / 60 if last_good else None
    if r.ok != 1 or age_min is None or age_min > MAX_AGE_MIN:
        stale.append((CHAIN_LABEL.get(chain, chain), age_min, r.error if r.ok != 1 else None))
kp = load("kpis", d0=d0, d1=d1, hours=hours)
if kp.empty or len(kp) < 2:
    md('<div class="enc"><h1>Cartelera CDMX: <span>Cinemex</span> frente a Cinépolis</h1></div>')
    st.info(f"No hay cartelera publicada de ambas cadenas para {range_es(d0, d1)}.")
    st.stop()
K = kp.set_index("chain")
us, them = K.loc["cinemex"], K.loc["cinepolis"]
last_capture = min(datetime.fromisoformat(r.taken_at) for _, r in last_ok.iterrows()) if len(last_ok) else None

md(f"""
<div class="enc">
  <h1>Cartelera CDMX: <span>Cinemex</span> frente a Cinépolis</h1>
  <div class="meta">
    <span><strong>Periodo:</strong> {esc(range_short(d0, d1))}</span>
    {"" if full_day else f"<span><strong>Franja:</strong> {esc(hours_label(hours))}</span>"}
    <span><strong>{int(us.cinemas)} + {int(them.cinemas)}</strong> cines</span>
    <span><strong>{int(us.shows + them.shows):,}</strong> funciones publicadas</span>
    <span>Última captura: {esc(local_time(last_capture.isoformat())) if last_capture else "—"}</span>
  </div>
  <nav class="nav-capas">
    <a href="#capa1"><b>1</b>Lo que importa hoy</a>
    <a href="#capa2"><b>2</b>Evidencia</a>
    <a href="#capa3"><b>3</b>Detalle</a>
  </nav>
</div>
""")
for name, age_min, err in stale:
    if age_min is None:
        st.warning(f"No hay ninguna captura buena de {name}.")
    elif err:
        st.warning(f"La última captura de {name} falló y el dato vigente tiene {age_min:.0f} minutos. Detalle técnico: {err[:120]}")
    else:
        st.warning(f"El dato de {name} tiene {age_min:.0f} minutos sin actualizarse; el scraper puede estar detenido.")

# ============ CAPA 1 ============
capa(1, "Lo que importa hoy",
     "Hallazgos redactados como decisión, cada uno con sus números de soporte. Si un dato no cambia una decisión "
     "esta semana, no vive aquí.", roja=True)
hallazgos = load_raw("findings", d0=d0, d1=d1, hours=hours)
if not hallazgos:
    st.info("Ninguna diferencia cruza el umbral de relevancia en este periodo. La evidencia completa está en la Capa 2.")
for f in hallazgos:
    hallazgo(f)
if any(f["topic"] == "dulceria" for f in hallazgos):
    st.page_link("views/dulceria.py", label="Ver el módulo de dulcería: precios en sala y a domicilio", icon=":material/fastfood:")

# ============ CAPA 2 ============
capa(2, "Evidencia por pregunta",
     "Cada sección abre con la conclusión; el gráfico es la prueba, no el mensaje. Las guías de lectura van colapsadas.")
concl = load_raw("conclusions", d0=d0, d1=d1, shown=SHOWN_MOVIES, total=TOTAL_MOVIES, hours=hours)

# --- Resumen general (formato del reporte diario del cliente) ------------------------------------------
with seccion("resumen"):
    pregunta("¿Cómo se reparte la programación de la semana?", concl.get("resumen", ""))
    tab_labels = list(HOUR_PRESETS)[:2]   # "Todo el día" y "Después de las 6 PM", lado a lado como en su reporte
    for tab, label in zip(st.tabs(tab_labels), tab_labels):
        with tab:
            gs = load("general_summary", d0=d0, d1=d1, hours=HOUR_PRESETS[label])
            if gs.empty:
                st.info("Sin funciones en el periodo.")
                continue
            rows_ = []
            rank = 0
            for r in gs.itertuples():
                cls = "sum" if r.kind != "title" else ""
                rank += r.kind == "title"
                name = {"title": r.title, "rest": "Resto", "total": "Total de programación"}[r.kind]

                def cell(txt, extra="", cls=cls):
                    return txt, " ".join(x for x in (extra, cls) if x)

                rows_.append([cell(str(rank) if r.kind == "title" else ""), cell(name),
                              cell(n(r.cinemas_cinemex) if r.kind != "rest" else "—", "cmx"), cell(n(r.shows_cinemex), "cmx"),
                              cell(f"{r.share_cinemex:.1f} %" if pd.notna(r.share_cinemex) else "—", "cmx"),
                              cell(n(r.cinemas_cinepolis) if r.kind != "rest" else "—", "cnp"), cell(n(r.shows_cinepolis), "cnp"),
                              cell(f"{r.share_cinepolis:.1f} %" if pd.notna(r.share_cinepolis) else "—", "cnp"),
                              cell(f"{int(r.diff_shows):+,d}".replace("-", "−")), cell(pp(r.diff_pp) if r.kind != "total" else ""),
                              cell(f"{r.ratio:.2f}" if pd.notna(r.ratio) else "—")])
            table(["", "Película", "Cines Cinemex", "Funciones", "% cadena", "Cines Cinépolis", "Funciones", "% cadena",
                   "Δ funciones", "Δ pp", "Cinépolis / Cinemex"], rows_, num_cols=range(2, 11))
    leerla("resumen",
           "Es la tabla del reporte diario, calculada para la Ciudad de México y la semana de cine (jueves a miércoles) del periodo "
           "elegido; el reporte del cliente es nacional y por semana calendario, así que las cifras no coinciden. Por cadena: cines "
           "que exhiben la película, funciones y qué parte de la programación de esa cadena representan. Δ funciones es Cinemex menos "
           "Cinépolis; Δ pp, la diferencia entre participaciones; la última columna, cuántas funciones pone Cinépolis por cada una "
           "nuestra. \"Resto\" agrupa las demás películas (sus cines no se suman porque se repiten). La pestaña de las 6 PM cuenta "
           "solo funciones que empiezan de 6:00 P.M. en adelante y no depende del filtro de franja de la barra lateral. Con el día en "
           "curso solo cuentan funciones que no han empezado.")

# --- Películas: dumbbell -------------------------------------------------------------------------------
with seccion("peliculas"):
    show_all = st.session_state.get("all_movies", False)
    pregunta("¿A qué películas les damos más pantalla que Cinépolis?", concl.get("peliculas", ""),
             None if show_all else concl.get("peliculas_note"))
    battle = load("movies_by_chain", d0=d0, d1=d1, limit=60, hours=hours)
    battle["title"] = battle["title"].str.strip()
    top = battle.head(TOTAL_MOVIES).copy()
    # Orden por magnitud de la diferencia; una exclusiva pesa lo que su propio share.
    top["abs_gap"] = top.apply(lambda r: r.share_cinemex if r.shows_cinepolis == 0 else
                               r.share_cinepolis if r.shows_cinemex == 0 else abs(r.gap_pp), axis=1)
    top = top.sort_values("abs_gap", ascending=False).head(TOTAL_MOVIES if show_all else SHOWN_MOVIES)
    order = top["title"].tolist()
    long = top.melt(id_vars=["title"], value_vars=["share_cinemex", "share_cinepolis"], var_name="chain", value_name="share")
    long["chain"] = long["chain"].str.replace("share_", "", regex=False)
    ti = top.set_index("title")
    long["shows"] = [ti.loc[t, f"shows_{c}"] for t, c in zip(long["title"], long["chain"])]
    long["cinemas"] = [ti.loc[t, f"cinemas_{c}"] for t, c in zip(long["title"], long["chain"])]
    long = long[long["shows"] > 0]
    long["Cadena"] = long["chain"].map(CHAIN_LABEL)
    top["delta"] = top.apply(lambda r: "solo Cinépolis" if r.shows_cinemex == 0 else
                             "solo Cinemex" if r.shows_cinepolis == 0 else pp(r.gap_pp), axis=1)
    top["gana"] = top.apply(lambda r: "cmx" if (r.shows_cinepolis == 0 or (r.shows_cinemex > 0 and r.gap_pp >= 0)) else "cnp", axis=1)
    leyenda([("Cinemex", RED), ("Cinépolis", INK)])
    y_axis = alt.Y("title:N", sort=order, title=None, axis=alt.Axis(labelLimit=300, labelColor=GRAY_DARK, labelFontSize=12.5,
                                                                    ticks=False, domain=False, labelPadding=10))
    color = alt.Color("Cadena:N", scale=alt.Scale(domain=CHAIN_DOMAIN, range=CHAIN_RANGE), legend=None)
    rule = alt.Chart(long).mark_rule(strokeWidth=2, color=NEUTRAL).encode(
        y=y_axis, x=alt.X("min(share):Q", title="% de las funciones del periodo", axis=alt.Axis(grid=True, tickCount=6)),
        x2="max(share):Q")
    dots = alt.Chart(long).mark_circle(size=120, opacity=1).encode(
        y=y_axis, x="share:Q", color=color,
        tooltip=[alt.Tooltip("title:N", title="Película"), alt.Tooltip("Cadena:N"),
                 alt.Tooltip("share:Q", title="% de su programación", format=".1f"),
                 alt.Tooltip("shows:Q", title="Funciones"), alt.Tooltip("cinemas:Q", title="Cines")])
    delta = alt.Chart(top).mark_text(align="left", fontSize=12.5, fontWeight="bold").encode(
        y=alt.Y("title:N", sort=order, axis=None), x=alt.value(4), text="delta:N",
        color=alt.Color("gana:N", scale=alt.Scale(domain=["cmx", "cnp"], range=[RED, GRAY_DARK]), legend=None),
        tooltip=[alt.Tooltip("title:N", title="Película"),
                 alt.Tooltip("share_cinemex:Q", title="% programación Cinemex", format=".1f"),
                 alt.Tooltip("share_cinepolis:Q", title="% programación Cinépolis", format=".1f"),
                 alt.Tooltip("gap_pp:Q", title="Δ pp (Cinemex − Cinépolis)", format="+.1f")]
    ).properties(width=110, height=alt.Step(24))
    chart(alt.hconcat((rule + dots).properties(width=620, height=alt.Step(24)), delta, spacing=6).resolve_scale(y="shared"))
    st.toggle(f"Ver las {TOTAL_MOVIES} películas", key="all_movies")
    leerla("peliculas",
           "Cada fila es una película; los puntos son el porcentaje de la programación que le dedica cada cadena y la "
           "línea entre ellos, la diferencia (rojo: Cinemex apuesta más). Un solo punto es una exclusiva. Se ordenan por "
           f"tamaño de la diferencia entre las {TOTAL_MOVIES} películas con más funciones del periodo; los títulos se emparejan "
           "por nombre, así que un reestreno puede aparecer como exclusiva de cada cadena.")

# --- Horarios: heatmap ---------------------------------------------------------------------------------
with seccion("horarios"):
    pregunta("¿Estamos en el horario donde vive la taquilla?", concl.get("franjas", ""))
    hm = load("heatmap_day_slot", d0=d0, d1=d1, hours=hours)
    if hm.empty:
        st.info("Sin funciones en el periodo.")
    else:
        hm["gap_pp"] = (hm["share_cinemex"].fillna(0) - hm["share_cinepolis"].fillna(0)).round(1)
        hm["Día"] = hm["weekday"].map(lambda i: WEEKDAY_LABEL[int(i)])
        hm["Franja"] = hm["slot"].map(SLOT_SHORT)
        hm["label"] = hm["gap_pp"].map(pp).str.replace(" pp", "")
        lim = max(1.0, float(hm["gap_pp"].abs().max()))
        days_present = [d for d in WEEKDAY_LABEL if d in set(hm["Día"])]
        base = alt.Chart(hm).encode(
            x=alt.X("Franja:N", sort=[SLOT_SHORT[k] for k, lo, hi, _ in SLOTS if lo >= hours[0] and hi <= hours[1]], title=None,
                    axis=alt.Axis(labelAngle=0, orient="top", labelFontSize=12, ticks=False, domain=False, labelPadding=6, labelOverlap=False, labelLimit=0)),
            y=alt.Y("Día:N", sort=days_present, title=None,
                    axis=alt.Axis(ticks=False, domain=False, labelFontSize=13, labelFontWeight="bold", labelColor=INK, labelPadding=10)))
        cells = base.mark_rect(stroke=PAPER, strokeWidth=4, cornerRadius=4).encode(
            color=alt.Color("gap_pp:Q", scale=alt.Scale(domain=[-lim, -lim / 2, 0, lim / 2, lim], range=DIVERGING, interpolate="lab"),
                            legend=None),
            tooltip=[alt.Tooltip("Día:N"), alt.Tooltip("Franja:N"),
                     alt.Tooltip("share_cinemex:Q", title="% parrilla Cinemex", format=".1f"),
                     alt.Tooltip("share_cinepolis:Q", title="% parrilla Cinépolis", format=".1f"),
                     alt.Tooltip("gap_pp:Q", title="Δ pp", format="+.1f"),
                     alt.Tooltip("shows_cinemex:Q", title="Funciones Cinemex"), alt.Tooltip("shows_cinepolis:Q", title="Funciones Cinépolis")])
        text = base.mark_text(fontSize=13.5, fontWeight="bold").encode(
            text="label:N", color=alt.condition(f"abs(datum.gap_pp) > {lim * 0.5}", alt.value(PAPER), alt.value(INK)))
        chart((cells + text).properties(height=alt.Step(46), width=alt.Step(134)), width="content")
    leerla("horarios",
           "Cada celda es la diferencia, en puntos porcentuales, entre la parte de parrilla que Cinemex pone en esa franja y "
           "la que pone Cinépolis. Rojo: ponemos más; oscuro: pone más Cinépolis. Solo aparecen los días del periodo elegido; "
           "la semana se completa cuando ambas cadenas la publican (miércoles o jueves). La ocupación real por franja se "
           "añadirá con el muestreo de asientos.")

# --- Formatos e idioma: barras -------------------------------------------------------------------------
with seccion("formatos"):
    pregunta("¿Con qué formatos e idiomas competimos?", concl.get("formatos", ""))
    mx = load("mix", d0=d0, d1=d1, hours=hours)
    if not mx.empty:
        mx["Cadena"] = mx["chain"].map(CHAIN_LABEL)
        m1, m2 = st.columns([3, 2])
        for col, dim, buckets, label_map, palette in ((m1, "format", FORMAT_BUCKETS, FORMAT_LABEL, RED_RAMP),
                                                      (m2, "language", LANGUAGE_BUCKETS, LANGUAGE_LABEL, [RED_RAMP[1], RED_RAMP[3]])):
            sub = mx[mx.dimension == dim].copy()
            sub["Grupo"] = sub["bucket"].map(label_map)
            sub["orden"] = sub["bucket"].map({b: i for i, b in enumerate(buckets)})
            sub["label"] = sub["share"].map(lambda v: f"{v:.0f} %" if v >= 7 else "")
            sub["light"] = sub["orden"] >= (2 if dim == "format" else 1)   # tonos claros: texto oscuro
            domain = [label_map[b] for b in buckets]
            with col:
                leyenda(list(zip(domain, palette)), square=True)
                bars = alt.Chart(sub).mark_bar(cornerRadius=0, stroke=PAPER, strokeWidth=1.5, height=26).encode(
                    y=alt.Y("Cadena:N", sort=CHAIN_DOMAIN, title=None,
                            axis=alt.Axis(ticks=False, domain=False, labelFontSize=13, labelFontWeight="bold", labelPadding=10,
                                          labelColor=alt.condition("datum.value == 'Cinemex'", alt.value(RED), alt.value(INK)))),
                    x=alt.X("share:Q", stack="normalize", title=None, axis=None),
                    order=alt.Order("orden:Q"),
                    color=alt.Color("Grupo:N", scale=alt.Scale(domain=domain, range=palette[:len(domain)]), legend=None),
                    tooltip=[alt.Tooltip("Cadena:N"), alt.Tooltip("Grupo:N"),
                             alt.Tooltip("share:Q", title="% de su programación", format=".1f"), alt.Tooltip("shows:Q", title="Funciones")])
                labels = alt.Chart(sub).mark_text(fontSize=11.5, fontWeight="bold").encode(
                    y=alt.Y("Cadena:N", sort=CHAIN_DOMAIN), x=alt.X("share:Q", stack="normalize", bandPosition=0.5),
                    order=alt.Order("orden:Q"), text="label:N", detail="Grupo:N",
                    color=alt.condition("datum.light", alt.value("#7A2233"), alt.value(PAPER)))
                chart((bars + labels).properties(height=90))
    leerla("formatos",
           "Cada barra es el 100 % de las funciones de una cadena en el periodo. Premium / VIP agrupa Premium, Platino, VIP y "
           "Confort; Gran formato agrupa IMAX, XE, ScreenX, Dolby Atmos y Jumbo. “Español” incluye doblada y en español original.")

# ============ CAPA 3 ============
capa(3, "Detalle y apéndice",
     "Todo colapsado con una línea de resumen visible: quien lo necesita lo abre, quien no, no paga el costo visual.")

# --- Indicadores del periodo (el antiguo KPI strip) --------------------------------------------------
offered = load("offered_seats", d0=d0, d1=d1, hours=hours).set_index("chain")
cc = load("concentration", d0=d0, d1=d1, hours=hours).set_index("chain") if True else None
cm = offered.loc["cinemex"] if "cinemex" in offered.index else None
cp = offered.loc["cinepolis"] if "cinepolis" in offered.index else None
resumen = f"{us.shows_per_cinema:.1f} vs {them.shows_per_cinema:.1f} funciones por cine y día"
if cm is not None and cp is not None and has(cm.seats_offered) and has(cp.seats_offered):
    resumen += f" · {int(cm.seats_offered):,} vs {int(cp.seats_offered):,} butacas ofertadas"
with apendice("kpis", "Indicadores del periodo", resumen):
    weekend = bool(us.weekend_shows and them.weekend_shows)
    rows = [
        ["Funciones por cine y día", n(us.shows_per_cinema, 1), n(them.shows_per_cinema, 1),
         f"{100.0 * (us.shows_per_cinema - them.shows_per_cinema) / them.shows_per_cinema:+.1f} %".replace("-", "−")],
        ["Funciones publicadas", n(us.shows), n(them.shows), ""],
        ["Cines con cartelera", n(us.cinemas), n(them.cinemas), ""],
        *([["Share de horario prime (vie–dom desde 6 PM)", f"{us.pct_prime:.1f} %", f"{them.pct_prime:.1f} %", pp(us.pct_prime - them.pct_prime)]
           if weekend else
           ["Share de 6 PM en adelante", f"{us.pct_evening:.1f} %", f"{them.pct_evening:.1f} %", pp(us.pct_evening - them.pct_evening)]]
          if full_day else []),
        ["Share de funciones subtituladas", f"{us.pct_subtitled:.1f} %", f"{them.pct_subtitled:.1f} %", pp(us.pct_subtitled - them.pct_subtitled)],
        ["Títulos distintos en cartelera", n(us.movies), n(them.movies), f"{int(us.movies - them.movies):+d}".replace("-", "−")],
    ]
    if cm is not None and cp is not None and has(cm.seats_offered) and has(cp.seats_offered):
        rows += [["Butacas ofertadas", n(cm.seats_offered), n(cp.seats_offered),
                  f"{100.0 * (cm.seats_offered - cp.seats_offered) / cp.seats_offered:+.1f} %".replace("-", "−")],
                 ["Butacas por función", n(cm.avg_seats_per_show), n(cp.avg_seats_per_show), ""]]
    if cc is not None and "cinemex" in cc.index and "cinepolis" in cc.index:
        rows += [["Peso de las 3 películas más programadas", f"{cc.loc['cinemex'].top3_pct:.1f} %", f"{cc.loc['cinepolis'].top3_pct:.1f} %",
                  pp(cc.loc["cinemex"].top3_pct - cc.loc["cinepolis"].top3_pct)],
                 ["Índice de concentración (HHI)", n(cc.loc["cinemex"].hhi), n(cc.loc["cinepolis"].hhi), ""],
                 ["Títulos distintos por complejo", n(cc.loc["cinemex"].titles_per_cinema, 1), n(cc.loc["cinepolis"].titles_per_cinema, 1), ""]]
    table(["Indicador", "Cinemex", "Cinépolis", "Δ"], [[r[0], (r[1], "cmx"), (r[2], "cnp"), r[3]] for r in rows], num_cols=(1, 2, 3))
    md('<p class="nota">Las diferencias entre porcentajes van en puntos porcentuales; las de cantidades, en % relativo. '
       'Butacas ofertadas = aforo de la sala por cada función del periodo (máximo de boletos vendibles), no butacas físicas. '
       'HHI: suma de los cuadrados del share de cada título; por debajo de 1,500 la parrilla está repartida, por encima de 2,500 concentrada.</p>')

# --- Cambios en la cartelera publicada -----------------------------------------------------------------
# Los cambios del competidor valen como comportamiento semanal, no como alerta: Cinemex programa por semana de cine.
CARTELERA_KINDS = [k for k in KINDS if k != "availability"]   # la ocupación es una medida, no un cambio de cartelera
by_kind = load("events_by_kind", since_hours=24 * 7)
ev = {(r.chain, r.kind): int(r.n) for r in by_kind.itertuples()} if not by_kind.empty else {}
g = lambda c, k: ev.get((c, k), 0)  # noqa: E731
resumen = (f"7 días: {g('cinemex', 'removed'):,} canceladas nuestras vs {g('cinepolis', 'removed'):,} de Cinépolis · "
           f"{g('cinemex', 'moved'):,} vs {g('cinepolis', 'moved'):,} cambios de horario o sala") if ev else "Sin cambios en los últimos 7 días"
with apendice("cambios", "¿Cómo ha movido Cinépolis su cartelera esta semana?", resumen):
    if ev:
        table(["Cadena", "Nuevas", "Canceladas", "Horario/sala", "Idioma/formato"],
              [[(CHAIN_LABEL[c], "cmx" if c == "cinemex" else "cnp")] + [f"{g(c, k):,}" for k in CARTELERA_KINDS] for c in CHAINS],
              num_cols=(1, 2, 3, 4))
    md('<p class="nota">Últimos 7 días. ' + " ".join(f"<b>{KIND_LABEL[k]}.</b> {KIND_HELP[k]}" for k in CARTELERA_KINDS) +
       " Cuando una cadena publica la semana siguiente (miércoles o jueves) aparecen miles de funciones nuevas de golpe; "
       "eso es publicación, no cambios sobre lo ya anunciado. Se lee como comportamiento semanal del competidor (cuánto cancela, "
       "de qué títulos, cuándo publica), no como alerta: la programación se decide por semana de cine.</p>")
    kinds = st.multiselect("Registro por función", CARTELERA_KINDS, default=CARTELERA_KINDS, format_func=lambda k: KIND_LABEL[k])
    events = load("recent_events", limit=300, kinds=kinds or None)
    if events.empty:
        st.info("Sin cambios de ese tipo.")
    else:
        st.dataframe(pretty(events.drop(columns=["show_id", "date"])), width="stretch", hide_index=True, height=360)

# --- Precios ---------------------------------------------------------------------------------------------
pr = load("prices")
if not pr.empty:
    P = {(r.chain, r.format_bucket, r.day_type): r.median_price for r in pr.itertuples()}

    def par(b, d):
        a, c = P.get(("cinemex", b, d)), P.get(("cinepolis", b, d))
        return f"{FORMAT_LABEL[b]} {DAY_TYPE_LABEL[d].lower()}: ${a:,.0f} vs ${c:,.0f}" if a and c else None
    bits = [x for x in (par("traditional", "promo"), par("premium", "weekend")) if x]
    ratios = [P[("cinepolis", b, d)] / P[("cinemex", b, d)] - 1 for b in ("traditional", "premium", "large") for d in ("weekday", "promo", "weekend")
              if ("cinemex", b, d) in P and ("cinepolis", b, d) in P and P[("cinemex", b, d)]]
    if ratios and min(ratios) > 0:
        bits.insert(0, f"Cinépolis cobra {100 * min(ratios):.0f}–{100 * max(ratios):.0f} % más en tradicional, premium y gran formato")
    with apendice("precios", "Precio del boleto por formato y tipo de día", " · ".join(bits)):
        rows = []
        for b in FORMAT_BUCKETS:
            for d in ("weekday", "promo", "weekend"):
                a, c = P.get(("cinemex", b, d)), P.get(("cinepolis", b, d))
                if a is None and c is None:
                    continue
                delta = f"{100.0 * (c - a) / a:+.0f} %".replace("-", "−") if a and c else ""
                rows.append([FORMAT_LABEL[b], DAY_TYPE_LABEL[d], (f"${a:,.0f}" if a else "—", "cmx"), (f"${c:,.0f}" if c else "—", "cnp"), delta])
        table(["Formato", "Tipo de día", "Cinemex", "Cinépolis", "Δ Cinépolis vs Cinemex"], rows, num_cols=(2, 3, 4))
        n_cin = pr.groupby("chain").cinemas.max()
        md('<p class="nota">Mediana del boleto de adulto regular entre los cines muestreados ('
           + ", ".join(f"{CHAIN_LABEL[c]}: {int(v)} cines" for c, v in n_cin.items())
           + "). Una función por cine, formato y tipo de día, renovada cada semana. Martes y miércoles son los días de precio "
             "reducido en ambas cadenas. Precios en pesos, sin cargo por servicio. Se excluyen eventos y matinés.</p>")
        st.dataframe(pretty(pr[["chain", "format_bucket", "day_type", "samples", "cinemas", "median_price", "min_price", "max_price"]]),
                     width="stretch", hide_index=True)

# --- Salas y butacas por complejo -------------------------------------------------------------------
cap = load("capacity_summary")
if not cap.empty:
    C = cap.set_index("chain")
    resumen = " · ".join(f"{CHAIN_LABEL[c]}: {int(r.screens)} salas, {int(r.seats):,} butacas, sala típica de {int(r.avg_seats)}"
                         for c, r in C.iterrows())
    with apendice("butacas", "Salas y butacas por complejo", resumen):
        table(["Cadena", "Complejos", "Salas", "Butacas", "Sala típica", "Más chica", "Más grande", "Salas < 80 (VIP)"],
              [[(CHAIN_LABEL[c], "cmx" if c == "cinemex" else "cnp"), n(r.cinemas), n(r.screens), n(r.seats), n(r.avg_seats),
                n(r.min_seats), n(r.max_seats), n(r.small)] for c, r in C.iterrows()], num_cols=range(1, 8))
        md('<p class="nota">Aforo medido una vez por sala en el plano de asientos de la función más próxima (se excluyen asientos '
           'fuera de servicio). Butacas físicas, no ofertadas.</p>')
        chain_sel = st.radio("Cadena", CHAINS, format_func=lambda c: CHAIN_LABEL[c], horizontal=True, key="cap_chain")
        c1, c2 = st.columns([3, 2])
        bt = load("offered_by_title", d0=d0, d1=d1, limit=TOTAL_MOVIES, chain=chain_sel, hours=hours)
        with c1:
            st.markdown(f"**Funciones frente a butacas por película ({CHAIN_LABEL[chain_sel]})**")
            if bt.empty:
                st.info("Sin funciones con aforo conocido en el periodo.")
            else:
                bt["title"] = bt["title"].str.strip()
                longb = bt.melt(id_vars=["title", "shows", "seats", "avg_seats"], value_vars=["share_shows", "share_seats"],
                                var_name="medida", value_name="share")
                longb["Medida"] = longb["medida"].map({"share_shows": "% de funciones", "share_seats": "% de butacas"})
                orderb = bt["title"].tolist()
                yb = alt.Y("title:N", sort=orderb, title=None, axis=alt.Axis(labelLimit=260, labelColor=GRAY_DARK, ticks=False, domain=False))
                ruleb = alt.Chart(longb).mark_rule(strokeWidth=2, color=NEUTRAL).encode(
                    y=yb, x=alt.X("min(share):Q", title=f"% del total de {CHAIN_LABEL[chain_sel]} en el periodo"), x2="max(share):Q")
                dotsb = alt.Chart(longb).mark_point(size=110, filled=True, opacity=1).encode(
                    y=yb, x="share:Q",
                    shape=alt.Shape("Medida:N", scale=alt.Scale(domain=["% de funciones", "% de butacas"], range=["circle", "square"]),
                                    legend=alt.Legend(orient="top", title=None)),
                    color=alt.Color("Medida:N", scale=alt.Scale(domain=["% de funciones", "% de butacas"], range=[NEUTRAL, CHAIN_COLOR[chain_sel]]),
                                    legend=alt.Legend(orient="top", title=None)),
                    tooltip=[alt.Tooltip("title:N", title="Película"), alt.Tooltip("Medida:N"),
                             alt.Tooltip("share:Q", title="%", format=".1f"), alt.Tooltip("shows:Q", title="Funciones"),
                             alt.Tooltip("seats:Q", title="Butacas", format=","), alt.Tooltip("avg_seats:Q", title="Butacas por sala")])
                chart((ruleb + dotsb).properties(height=alt.Step(24)))
                md('<p class="nota">El círculo claro es la parte de las funciones de la cadena que ocupa la película; el cuadro, la parte de '
                   'sus butacas ofertadas. Cuando el cuadro queda a la derecha, la película va en salas más grandes que el promedio.</p>')
        with c2:
            st.markdown("**Salas y butacas por complejo**")
            bc = load("capacity_by_cinema", chain=chain_sel)
            st.dataframe(pretty(bc[["cinema_name", "screens", "seats", "avg_seats", "min_seats", "max_seats"]]),
                         width="stretch", hide_index=True, height=420)

# --- Historial de una función y cartelera tal como estaba ------------------------------------------------
with apendice("historia", "Historial de una función y cartelera tal como estaba",
              f"elige cine, fecha y sala · historia desde el {date_es(FIRST_SNAPSHOT.isoformat())}"):
    md('<p class="nota" style="margin-top:0">Qué le pasó a cada función (cuándo se publicó, cambios de hora, sala, idioma o formato, '
       'cancelación) y cómo estaba la cartelera de esa sala en cualquier captura anterior. La reconstrucción es exacta desde el 9 de '
       'septiembre de 2026; antes, las funciones ya concluidas no dejaban rastro.</p>')
    h1, h2, h3, h4 = st.columns([1, 2, 1.4, 1])
    chain_h = h1.selectbox("Cadena", CHAINS, format_func=lambda c: CHAIN_LABEL[c], key="h_chain")
    cins = load("cinemas", chain=chain_h)
    cine_h = h2.selectbox("Cine", cins.cinema_id.tolist(), format_func=dict(zip(cins.cinema_id, cins.cinema_name)).get, key="h_cine")
    dates_h = load("dates_known", chain=chain_h, cinema_id=cine_h).date.tolist()
    fecha_h = h3.selectbox("Fecha", dates_h, index=dates_h.index(today_s) if today_s in dates_h else max(len(dates_h) - 1, 0),
                           format_func=lambda d: date_es(d, with_year=False), key="h_date")
    fo = load("functions_on", chain=chain_h, cinema_id=cine_h, date=fecha_h)
    if fo.empty:
        st.info("Sin funciones conocidas para ese cine y fecha.")
    else:
        screens = sorted(fo.screen.dropna().unique(), key=lambda x: (len(str(x)), str(x)))
        sala_h = h4.selectbox("Sala", ["Todas"] + list(screens), key="h_screen")
        sub = fo if sala_h == "Todas" else fo[fo.screen == sala_h]
        st.markdown(f"**Funciones conocidas · {len(sub)}** ({int((sub.status == 'current').sum())} vigentes, "
                    f"{int((sub.status == 'removed').sum())} canceladas, {int((sub.status == 'expired').sum())} concluidas)")
        st.dataframe(pretty(sub[["datetime_local", "screen", "movie_title", "language", "format", "status", "first_seen"]]),
                     width="stretch", hide_index=True, height=min(400, 38 * (len(sub) + 1)))
        opciones = {r.show_id: f"{time_12(r.datetime_local[11:16])} · sala {r.screen} · {r.movie_title}" for r in sub.itertuples()}
        show_h = st.selectbox("Función", list(opciones), format_func=opciones.get, key="h_show")
        tl = load_raw("showtime_timeline", chain=chain_h, show_id=show_h, date=fecha_h)
        st.markdown("**Línea de tiempo de la función**")
        if not tl:
            st.info("Sin eventos registrados para esta función.")
        else:
            def cambio(ch):
                fmt = (lambda v: time_12(v[11:16]) if isinstance(v, str) and len(v) >= 16 else (v or "—")) if ch["field"] == "datetime_local" else (lambda v: v or "—")
                return f"{FIELD_LABEL.get(ch['field'], ch['field'])}: {fmt(ch['before'])} → {fmt(ch['after'])}"
            table(["Cuándo", "Qué pasó", "Detalle"],
                  [[local_time(e["detected_at"]), KIND_LABEL.get(e["kind"], e["kind"]), "; ".join(cambio(ch) for ch in e["changes"])] for e in tl])
        first = tl[0]["detected_at"] if tl else FIRST_SNAPSHOT.isoformat()
        snaps = load("snapshot_times", chain=chain_h, since=first, until=datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        st.markdown("**Cartelera de la sala tal como estaba en una captura**")
        if len(snaps) < 2:
            st.info("Hace falta más de una captura desde que se publicó la función para reconstruir la cartelera.")
        else:
            opts = snaps.taken_at.tolist()
            as_of = st.select_slider("Captura", options=opts, value=opts[-1], format_func=local_time, key="h_asof")
            board = load("board_as_of", chain=chain_h, cinema_id=cine_h, date=fecha_h, as_of=as_of)
            if sala_h != "Todas":
                board = board[board.screen == sala_h]
            if board.empty:
                st.info("En esa captura no había funciones publicadas para esta sala y fecha.")
            else:
                board["changes"] = board["changed_fields"].map(lambda fs: ", ".join(FIELD_LABEL.get(f, f) for f in fs) if isinstance(fs, list) else "")
                st.dataframe(pretty(board[["datetime_local", "screen", "movie_title", "language", "format", "availability", "vs_now", "changes"]]),
                             width="stretch", hide_index=True, height=min(400, 38 * (len(board) + 1)))
                md('<p class="nota">"Frente a hoy" compara cada función con la cartelera vigente: igual, cambió después (y en qué) o ya no '
                   'está publicada. Mueve el control para ver la cartelera en capturas anteriores.</p>')

# --- Ocupación muestreada -----------------------------------------------------------------------------
occ = load("occupancy_summary")
cal = load("semaphore_calibration", chain="cinemex")
n_samples = int(occ.samples.sum()) if not occ.empty else 0
weighted = 100.0 * occ.sold.sum() / occ.seats.sum() if n_samples and occ.seats.sum() else 0.0
levels = int((occ.availability != "(sin color)").sum()) if n_samples else 0
resumen = (f"{n_samples} funciones medidas de Cinépolis · {weighted:.1f} % de butacas vendidas en promedio · "
           + (f"{levels} niveles de color para calibrar" if levels else "aún sin semáforos de color para calibrar")
           + (" · semáforo de Cinemex calibrado" if not cal.empty else " · semáforo de Cinemex sin calibrar"))
with apendice("ocupacion", "Ocupación medida tras el inicio de cada función", resumen):
    if n_samples == 0:
        st.info("Aún no hay medidas. El pase corre cada hora y lee el plano de las funciones de Cinépolis que empezaron hace 15 a 75 minutos.")
    else:
        st.markdown(f"**Cinépolis.** {n_samples} funciones medidas después de empezar; {weighted:.1f} % de las butacas vendidas. Es la "
                    "asistencia final de cada función y la base del modelo de consumo. La tabla cruza el color del semáforo del sitio con "
                    "el porcentaje real vendido, para calibrar qué significa cada color.")
        st.dataframe(pretty(occ[["availability", "samples", "avg_sold_pct", "min_sold_pct", "max_sold_pct"]]), width="stretch", hide_index=True)
    if cal.empty:
        st.markdown("**Cinemex.** Publica alta, media o baja disponibilidad por función. Al calibrar cada nivel contra planos reales "
                    "(una pasada única, por la tarde-noche, cuando existen los tres niveles) el semáforo se convierte en % vendido "
                    "estimado para todas sus funciones.")
    else:
        est = load("estimated_occupancy", d0=d0, d1=d1, chain="cinemex", hours=hours)
        if not est.empty and has(est.iloc[0].seats_occupied_est):
            e = est.iloc[0]
            st.markdown(f"**Cinemex.** {int(e.seats_occupied_est):,} butacas ocupadas estimadas de {int(e.seats_offered):,} ofertadas en el "
                        f"periodo ({e.occupancy_pct_est:.1f} %), a partir del nivel de disponibilidad de cada función y su calibración "
                        f"({int(e.shows_estimated):,} de {int(e.shows):,} funciones estimables).")
        st.dataframe(pretty(cal.rename(columns={"level": "availability"})[["availability", "samples", "sold_pct", "min_sold_pct", "max_sold_pct"]]),
                     width="stretch", hide_index=True)
    if n_samples:
        st.markdown("**Últimas funciones medidas (Cinépolis)**")
        st.dataframe(pretty(load("occupancy_recent", limit=30)), width="stretch", hide_index=True, height=300)
    md('<p class="nota">Se promueve a Capa 2 cuando la tabla de calibración tenga niveles de color con muestras suficientes. '
       'Mientras tanto no compite por atención.</p>')

# --- Desbloqueo -------------------------------------------------------------------------------------------
decay_eta = FIRST_SNAPSHOT + timedelta(weeks=2) + timedelta(days=(3 - FIRST_SNAPSHOT.weekday()) % 7)
trend_eta = FIRST_SNAPSHOT + timedelta(weeks=4)


def fecha_corta(d):
    return range_short(d.isoformat(), d.isoformat()).split(" ", 1)[1]


items = [
    ("Con tu taquilla por título", "Abrir, mantener o recortar por película",
     "Regla lista: 2 pp bajo su demanda y ≥5 % de butacas → abrir; 2 pp arriba → recortar."),
    ("Con tu preventa (batch)", "Curva de preventa vs títulos comparables",
     "Evita cerrar salas que se llenarían de paso comparando contra la banda histórica correcta."),
    ("Con tu lista de dulcería", "Brecha de precio de dulcería por complejo y zona",
     "Ya tenemos el menú de Cinépolis con precio por complejo (74 en la ciudad); tu lista lo convierte en brecha por producto y zona."),
    ("Con tu taquilla por función", "Ingreso por butaca ofertada, real frente a potencial",
     "Ya tenemos aforo, mix de formato y precio de lista de ambas cadenas; tu taquilla convierte el potencial en ingreso real."),
    (f"Automático · {fecha_corta(decay_eta)}", "Decaimiento post-estreno por cadena",
     "Quién recorta agresivo y quién conserva, con dos semanas de cine completas de historia."),
    (f"Automático · {fecha_corta(trend_eta)}", "Tendencia de 4 semanas por indicador",
     "Responde “¿vamos mejorando?” en cada indicador del periodo."),
    ("Captura adicional", "Hueco geográfico por alcaldía",
     "Oferta por 100 mil habitantes, zonas de choque y mercados cautivos; falta alcaldía por cine y población INEGI."),
]
if cal.empty:
    items.insert(3, ("Pasada manual · tarde-noche", "Ocupación estimada de Cinemex",
                     "Una calibración del semáforo alta/media/baja contra planos reales convierte cada función en % vendido."))
md('<div class="desbloqueo"><h3>Qué se desbloquea con tus datos</h3>'
   '<p>Todo lo que hoy requiere integración, captura o historia se agrupa aquí, convertido en argumento: qué decisión habilita '
   'cada dato y cuándo estará listo lo que depende solo de nosotros.</p><div class="desb-grid">'
   + "".join(f'<div class="desb-item"><div class="cuando">{esc(a)}</div><div class="que">{esc(b)}</div><p>{esc(c)}</p></div>' for a, b, c in items)
   + "</div></div>")

md(f'<p class="pie">Fuentes: cartelera pública de Cinemex y Cinépolis, capturada tres veces al día para los cines de la Ciudad de México '
   f'y área metropolitana; aforo por sala de ambas cadenas leído de los planos de asientos; ocupación medida tras el inicio de cada '
   f'función en Cinépolis; precios de lista muestreados por cine, formato y tipo de día; menú de dulcería de Cinépolis con precio por complejo; catálogo de dulcería a domicilio de ambas cadenas en Rappi y DiDi Food. Las películas se emparejan por título hasta '
   f'contar con la tabla de equivalencias entre cadenas.{"" if full_day else f" Filtro activo: solo funciones que empiezan {esc(hours_label(hours))}."} Historia desde el {esc(date_es(FIRST_SNAPSHOT.isoformat()))}.</p>')
