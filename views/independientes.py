"""Página de la oferta independiente: la Cineteca Nacional frente a nuestra cartelera de CDMX, fuera del head-to-head
con Cinépolis. Tres capas como la cartelera, con su propio selector de periodo (la Cineteca publica hasta el miércoles
de la semana en curso). Solo tiene sedes en CDMX: con otra plaza la página avisa y se detiene. La ocupación queda
pendiente mientras la lectura de sus planos no esté confirmada (`analytics.independents.OCCUPANCY_CONFIRMED`)."""
from ui.common import *  # noqa: F401,F403

T = INDEP_TEXT
INDEP_CHAIN = "cineteca"
confirmed = analytics.independents.OCCUPANCY_CONFIRMED

if not config.DB_PATH.exists():
    st.info(T["no_db"])
    st.stop()

plaza = plaza_selector()
if plaza not in (None, "cdmx"):
    md(f'<div class="enc"><h1>{T["title"]}</h1></div>')
    st.info(T["no_plaza"])
    st.stop()

# --- barra lateral: periodo dentro de la semana de cine en curso -----------------------------------------------
today_s = analytics.today()
today_d = date.fromisoformat(today_s)
this_w0, this_w1 = analytics.cinema_week(today_s)
periods = {
    T["period_today"]: (today_s, today_s),
    T["period_tomorrow"]: ((today_d + timedelta(days=1)).isoformat(),) * 2,
    T["period_week"].format(d1=date_es(this_w1, with_year=False)): (today_s, this_w1),
    T["period_pick"]: None,
}
st.sidebar.header(T["period_header"])
choice = st.sidebar.radio(T["period_header"], list(periods), index=2, label_visibility="collapsed", key="indep_period")
if periods[choice] is None:
    rng = st.sidebar.date_input(T["period_range"], value=(today_d, date.fromisoformat(this_w1)),
                                min_value=today_d - timedelta(days=1), max_value=date.fromisoformat(this_w1), format="DD/MM/YYYY")
    d0, d1 = (rng[0].isoformat(), rng[-1].isoformat()) if isinstance(rng, tuple) and rng else (today_s, today_s)
else:
    d0, d1 = periods[choice]
st.sidebar.caption(T["period_caption"])

venues = load("independent_summary", d0=d0, d1=d1)
if venues.empty:
    md(f'<div class="enc"><h1>{T["title"]}</h1></div>')
    st.info(T["no_data"].format(period=range_es(d0, d1)))
    st.stop()

concl = load_raw("independent_conclusions", d0=d0, d1=d1)
hallazgos = [f for f in load_raw("findings", d0=d0, d1=d1, top=20, plaza=plaza) if f["topic"] == "independientes"]

md(f"""
<div class="enc">
  <h1>{T["title"]}</h1>
  <div class="meta">
    <span><strong>{esc(T["meta_zone"])}:</strong> {esc(T["meta_zone_value"])}</span>
    <span><strong>{esc(T["meta_period"])}:</strong> {esc(range_es(d0, d1))}</span>
    <span>{esc(T["meta_note"])}</span>
  </div>
</div>
""")

# --- Capa 1 ---------------------------------------------------------------------------------------------------
capa(1, T["layer1"], T["layer1_desc"], roja=True)
if not hallazgos:
    st.info(T["layer1_none"].format(pct=f"{analytics.independents.INDEP_MIN_SOLD_PCT:.0f}", n=analytics.independents.INDEP_MIN_SAMPLES)
            if confirmed else T["layer1_pending"])
for f in hallazgos:
    hallazgo(f)

# --- Capa 2 ---------------------------------------------------------------------------------------------------
capa(2, T["layer2"], T["layer2_desc"])
indep_legend = [(CHAIN_LABEL[INDEP_CHAIN], INDEP)]

with seccion("indep-programa"):
    pregunta(T["q_programa"], concl.get("programa", ""), T["programa_note"])
    titles = load("independent_titles", d0=d0, d1=d1, limit=15)
    leyenda(indep_legend)
    st.markdown(f"**{T['programa_chart']}**")
    bars = alt.Chart(titles).mark_bar(color=INDEP).encode(
        y=alt.Y("title:N", sort=None, title=None, axis=alt.Axis(labelLimit=260, labelColor=GRAY_DARK, ticks=False, domain=False)),
        x=alt.X("share_shows:Q", title=COLUMN_LABEL["share_shows"]),
        tooltip=[alt.Tooltip("title:N", title=COLUMN_LABEL["title"]), alt.Tooltip("shows:Q", title=COLUMN_LABEL["shows"]),
                 alt.Tooltip("cinemas:Q", title=COLUMN_LABEL["cinemas"]), alt.Tooltip("share_shows:Q", title=COLUMN_LABEL["share_shows"], format=".1f")])
    chart(bars.properties(height=alt.Step(22)))
    st.dataframe(pretty(venues[["cinema_name", "shows", "titles", "days", "share_shows"]]), width="stretch", hide_index=True)
    leerla("indep-programa", T["leer_programa"])

with seccion("indep-ocupacion"):
    occ = load("occupancy_by_cinema", days=analytics.independents.OCCUPANCY_DAYS, chain=INDEP_CHAIN)
    measured = int(occ.samples.sum()) if not occ.empty else 0
    enough = confirmed and measured >= analytics.independents.OCCUPANCY_MIN_SAMPLES
    pregunta(T["q_ocupacion"], concl.get("ocupacion", "") if enough else "")
    if not confirmed:
        st.info(T["ocupacion_pending"])
    elif not enough:
        st.info(T["ocupacion_few"].format(n=measured, min=analytics.independents.OCCUPANCY_MIN_SAMPLES))
    else:
        leyenda(indep_legend)
        st.markdown(f"**{T['ocupacion_chart']}**")
        occ["Franja"] = occ["slot"].map(SLOT_SHORT)
        heat = alt.Chart(occ).mark_rect().encode(
            x=alt.X("Franja:N", sort=[SLOT_SHORT[k] for k, *_ in SLOTS], title=None),
            y=alt.Y("cinema_name:N", title=None),
            color=alt.Color("sold_pct:Q", scale=alt.Scale(range=[GRAY_LIGHT, INDEP]), legend=alt.Legend(title=COLUMN_LABEL["sold_pct"])),
            tooltip=[alt.Tooltip("cinema_name:N", title=COLUMN_LABEL["cinema_name"]), alt.Tooltip("Franja:N"),
                     alt.Tooltip("samples:Q", title=COLUMN_LABEL["samples"]), alt.Tooltip("sold_pct:Q", title=COLUMN_LABEL["sold_pct"], format=".1f")])
        chart(heat.properties(height=alt.Step(40)))
        by_title = load("occupancy_by_title", days=analytics.independents.OCCUPANCY_DAYS, chain=INDEP_CHAIN,
                        min_samples=analytics.independents.INDEP_MIN_SAMPLES)
        if not by_title.empty:
            st.markdown(f"**{T['ocupacion_titles']}**")
            st.dataframe(pretty(by_title.sort_values(["sold_pct", "title_norm"], ascending=[False, True])[["title", "samples", "sold_pct"]]),
                         width="stretch", hide_index=True)
    leerla("indep-ocupacion", T["leer_ocupacion"])

with seccion("indep-solape"):
    pregunta(T["q_solape"], concl.get("solape", ""))
    overlap = load("independent_overlap", d0=d0, d1=d1)
    overlap["Estado"] = overlap["status"].map(T["status"])
    status_domain = [T["status"]["shared"], T["status"]["indep_only"]]
    leyenda([(status_domain[0], CHAIN_COLOR["cinemex"]), (status_domain[1], INDEP)])
    st.markdown(f"**{T['solape_chart']}**")
    top_overlap = overlap.head(15)
    bars = alt.Chart(top_overlap).mark_bar().encode(
        y=alt.Y("title:N", sort=None, title=None, axis=alt.Axis(labelLimit=260, labelColor=GRAY_DARK, ticks=False, domain=False)),
        x=alt.X("share_indep:Q", title=COLUMN_LABEL["share_indep"]),
        color=alt.Color("Estado:N", scale=alt.Scale(domain=status_domain, range=[CHAIN_COLOR["cinemex"], INDEP]), legend=None),
        tooltip=[alt.Tooltip("title:N", title=COLUMN_LABEL["title"]), alt.Tooltip("Estado:N"),
                 alt.Tooltip("shows_indep:Q", title=COLUMN_LABEL["shows_indep"]), alt.Tooltip("shows_vs:Q", title=COLUMN_LABEL["shows_vs"])])
    chart(bars.properties(height=alt.Step(22)))
    only = overlap[overlap.status == "indep_only"]
    if not only.empty:
        st.markdown(f"**{T['solape_only']}**")
        cols = ["title", "shows_indep", "share_indep"] + (["samples", "sold_pct"] if enough else [])
        st.dataframe(pretty(only[cols]), width="stretch", hide_index=True, height=min(400, 38 * (len(only) + 1)))
    leerla("indep-solape", T["leer_solape"])

with seccion("indep-franjas"):
    pregunta(T["q_franjas"], concl.get("franjas", ""))
    slots = load("independent_slots", d0=d0, d1=d1)
    chains_here = [c for c in ("cinemex", INDEP_CHAIN) if c in set(slots.chain)]
    leyenda([(CHAIN_LABEL[c], CHAIN_COLOR[c]) for c in chains_here])
    st.markdown(f"**{T['franjas_chart']}**")
    slots["Cadena"] = slots["chain"].map(CHAIN_LABEL)
    slots["Franja"] = slots["slot"].map(SLOT_SHORT)
    domain = [CHAIN_LABEL[c] for c in chains_here]
    grouped = alt.Chart(slots).mark_bar().encode(
        x=alt.X("Franja:N", sort=[SLOT_SHORT[k] for k, *_ in SLOTS], title=None, axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("Cadena:N", sort=domain),
        y=alt.Y("share:Q", title=COLUMN_LABEL["share"]),
        color=alt.Color("Cadena:N", scale=alt.Scale(domain=domain, range=[CHAIN_COLOR[c] for c in chains_here]), legend=None),
        tooltip=[alt.Tooltip("Cadena:N"), alt.Tooltip("Franja:N"), alt.Tooltip("shows:Q", title=COLUMN_LABEL["shows"]),
                 alt.Tooltip("share:Q", title=COLUMN_LABEL["share"], format=".1f")])
    chart(grouped.properties(height=260))
    leerla("indep-franjas", T["leer_franjas"])

# --- Capa 3 ---------------------------------------------------------------------------------------------------
capa(3, T["layer3"], T["layer3_desc"])
board = load("independent_titles", d0=d0, d1=d1, limit=1000)
with apendice("indep-cartelera", T["app_board"], T["app_board_summary"].format(titles=n(len(board)), shows=n(board.shows.sum()))):
    st.dataframe(pretty(board[["title", "shows", "cinemas", "share_shows", "spanish", "subtitled", "other", "first_date", "last_date"]]),
                 width="stretch", hide_index=True, height=min(500, 38 * (len(board) + 1)))

cap = load("capacity_by_cinema", chain=INDEP_CHAIN)
cap_summary = T["app_capacity_summary"].format(screens=n(cap.screens.sum()), cinemas=n(len(cap))) if not cap.empty else ""
with apendice("indep-aforo", T["app_capacity"], cap_summary):
    if cap.empty:
        st.info(T["app_capacity_empty"])
    else:
        st.dataframe(pretty(cap[["cinema_name", "screens", "seats", "avg_seats", "min_seats", "max_seats"]]), width="stretch", hide_index=True)

with apendice("indep-pendientes", T["app_pending"], T["app_pending_summary"]):
    st.markdown("\n".join(f"- {item}" for item in T["pending_items"]))

st.page_link("views/cartelera.py", label=T["back"], icon=":material/movie:")
md(f'<p class="pie">{esc(T["footer"].format(first=date_es(FIRST_SNAPSHOT.isoformat())))}</p>')
