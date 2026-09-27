"""Página del mapa de cines: cada complejo de Cinemex, Cinépolis y la Cineteca en su lugar, con su ficha (funciones,
salas, butacas, boleto, palomitas, ocupación) y los destacados de cada cadena en la zona. El tamaño del punto sigue la
métrica elegida. Los datos salen de `analytics/cinema_locations.py` (`cinema_map`, `cinema_highlights`); aquí solo se pintan."""
import math

import pydeck as pdk

from ui.common import *  # noqa: F401,F403

T = MAP_TEXT
_MIN_RADIUS, _MAX_RADIUS = 5, 22         # píxeles: no crecen con el zoom, así los cines vecinos no se tapan
_SPREAD = 0.0012                         # grados (~130 m): cuánto se abren los cines que comparten edificio
_ZOOM = {None: 4.3}                        # nacional; una plaza se ve completa con el zoom por defecto
_DEFAULT_ZOOM = 9.6
_SPAN_ZOOM = ((0.01, 14), (0.05, 12.5), (0.15, 11), (0.4, 10), (2, 8), (float("inf"), 4.3))   # grados de separación → zoom

if not config.DB_PATH.exists():
    st.info(T["no_db"])
    st.stop()

plaza = plaza_selector()
today_s = analytics.today()
d0, d1 = today_s, analytics.cinema_week(today_s)[1]

st.sidebar.header(T["size_by"])
metric = st.sidebar.radio(T["size_by"], list(MAP_METRIC), format_func=lambda m: MAP_METRIC[m][0], key="map_metric",
                          label_visibility="collapsed")
st.sidebar.caption(T["size_help"])
st.sidebar.header(T["chains"])
chains = tuple(c for c in CHAIN_LABEL if st.sidebar.checkbox(CHAIN_LABEL[c], value=True, key=f"map_{c}"))
if not chains:
    st.info(T["no_chains"])
    st.stop()

zone = load("cinema_map", d0=d0, d1=d1, plaza=plaza, chains=chains)
names = {r.cinema_id: f"{CHAIN_LABEL[r.chain]} · {r.cinema_name}" for r in zone.itertuples()} if not zone.empty else {}
st.sidebar.header(T["cinemas"])
# Al cambiar de zona o de cadenas, los cines elegidos que ya no están en la lista se sueltan.
st.session_state["map_cinemas"] = [c for c in st.session_state.get("map_cinemas", []) if c in names]
picked_ids = st.sidebar.multiselect(T["cinemas"], options=list(names), format_func=names.get, key="map_cinemas",
                                    placeholder=T["cinemas_placeholder"], help=T["cinemas_help"], label_visibility="collapsed")
cinema_ids = tuple(picked_ids) or None
cinemas = load("cinema_map", d0=d0, d1=d1, plaza=plaza, chains=chains, cinema_ids=cinema_ids) if cinema_ids else zone
md(f"""
<div class="enc">
  <h1>{T["title"]}</h1>
  <div class="meta">
    <span><strong>{esc(T["meta_zone"])}:</strong> {esc(PLAZA_LABEL.get(plaza, plaza) if plaza else NATIONAL_LABEL)}</span>
    <span><strong>{esc(T["meta_period"])}:</strong> {esc(range_es(d0, d1))}</span>
    <span>{esc(T["filtered"].format(n=n(len(cinemas)), total=n(len(zone))) if cinema_ids else T["meta_note"])}</span>
  </div>
</div>
""")
if cinemas.empty:
    st.info(T["empty"])
    st.stop()
chains = tuple(c for c in chains if c in set(cinemas.chain))


def zoom_for(data, plaza, cinema_ids):
    """Zoom de la zona completa, o el que encuadra los cines elegidos (más cerca cuanto menos separados estén)."""
    if not cinema_ids:
        return _ZOOM.get(plaza, _DEFAULT_ZOOM)
    span = max(data.lat.max() - data.lat.min(), data.lng.max() - data.lng.min())
    return next(z for limit, z in _SPAN_ZOOM if span <= limit)


def fmt(m, v):
    return MAP_METRIC[m][1].format(v) if has(v) else T["no_value"]


def value_text(cinema, m):
    """Valor de una métrica de un cine; el boleto más caro dice de qué formato es."""
    text = fmt(m, cinema[m])
    if m == "ticket_max" and has(cinema[m]) and cinema.get("ticket_max_format"):
        text += f" ({FORMAT_LABEL.get(cinema['ticket_max_format'], cinema['ticket_max_format'])})"
    return text


def cell(cinema, m):
    """Valor de una métrica de un cine para la ficha; el boleto lleva la fecha de su lectura."""
    text = value_text(cinema, m)
    sampled = {"ticket_price": "ticket_sampled_at", "ticket_max": "ticket_max_sampled_at"}.get(m)
    if sampled and has(cinema[m]) and cinema[sampled]:
        text += f", {T['sampled'].format(date=date_es(cinema[sampled][:10], with_year=False))}"
    return text


def tip(site):
    """Tooltip de un lugar en texto plano, el mismo para cada cine del edificio: la cadena, cuántos cines hay y, por
    cada uno, su nombre y sus métricas. Va como texto (saltos de línea) y no como HTML porque Streamlit escapa el HTML
    que viene en los datos."""
    k = len(site["cinemas"])
    head = CHAIN_LABEL[site["chain"]] + (f" · {T['site_count'].format(n=k)}" if k > 1 else "")
    blocks = [f"{r['cinema_name']}\n" + "\n".join(f"  {MAP_METRIC[m][0]}: {value_text(r, m)}" for m in MAP_METRIC)
              for r in site["cinemas"]]
    return f"{head}\n\n" + "\n\n".join(blocks)


def points(sites, metric):
    """Un punto por cine. Los cines de un mismo edificio se abren en círculo alrededor de su coordenada real, para que
    se vean todos; cada uno lleva el tooltip de su edificio completo."""
    out = []
    for site in sites:
        k = len(site["cinemas"])
        for i, r in enumerate(site["cinemas"]):
            angle = 2 * math.pi * i / k
            shift = _SPREAD if k > 1 else 0.0
            out.append({"site_id": site["site_id"], "chain": r["chain"], "cinema_id": r["cinema_id"], "value": r[metric],
                        "lat": r["lat"] + shift * math.sin(angle), "lng": r["lng"] + shift * math.cos(angle), "tip": tip(site)})
    return pd.DataFrame(out)


# --- destacados --------------------------------------------------------------------------------------------------
with seccion("mapa-destacados"):
    pregunta(T["highlights"], T["highlights_desc"])
    hl = load("cinema_highlights", d0=d0, d1=d1, plaza=plaza, chains=chains, cinema_ids=cinema_ids)
    shown = [c for c in CHAIN_LABEL if c in chains and not hl.empty and c in set(hl.chain)]
    rows_ = []
    for m in MAP_METRIC:
        cells = [MAP_METRIC[m][2]]
        for c in shown:
            r = hl[(hl.metric == m) & (hl.chain == c)]
            cells.append((f"{r.iloc[0].cinema_name} · {fmt(m, r.iloc[0].value)} ({int(r.iloc[0].cinemas)})", "cmx" if c == "cinemex" else "")
                         if not r.empty else "—")
        rows_.append(cells)
    table([""] + [CHAIN_LABEL[c] for c in shown], rows_)
    if "cinepolis" in shown:
        md(f'<p class="nota">{esc(T["popcorn_note"])}</p>')

# --- mapa ----------------------------------------------------------------------------------------------------------
with seccion("mapa-mapa"):
    pregunta(T["map"], T["map_desc"])
    leyenda([(CHAIN_LABEL[c], CHAIN_COLOR[c]) for c in chains])
    sites = load_raw("cinema_sites", d0=d0, d1=d1, plaza=plaza, chains=chains, cinema_ids=cinema_ids)
    data = points(sites, metric)
    top = data["value"].max() if data["value"].notna().any() else None
    known = data["value"].notna() & (data["value"] > 0)
    data["radius"] = float(_MIN_RADIUS)
    if top:
        data.loc[known, "radius"] = _MIN_RADIUS + (_MAX_RADIUS - _MIN_RADIUS) * data.loc[known, "value"] / top
    data["color"] = [rgb(CHAIN_COLOR[c], 215 if k else 70) for c, k in zip(data.chain, known)]
    tooltip = {"text": "{tip}",
               "style": {"backgroundColor": PAPER, "color": INK, "fontSize": "12px", "border": f"1px solid {LINE}",
                         "whiteSpace": "pre", "lineHeight": "1.45"}}
    layer = pdk.Layer("ScatterplotLayer", data=data, id="cines",
                      get_position=["lng", "lat"], get_radius="radius", get_fill_color="color",
                      radius_units="'pixels'",   # pydeck toma un texto suelto como expresión JS: el literal va entre comillas
                      get_line_color=rgb(PAPER), line_width_min_pixels=1, stroked=True, pickable=True, auto_highlight=True)
    view = pdk.ViewState(latitude=float(data.lat.mean()), longitude=float(data.lng.mean()), zoom=zoom_for(data, plaza, cinema_ids))
    event = st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip=tooltip, map_style=BASEMAP_STYLE),
                            on_select="rerun", selection_mode="single-object", key="map", height=560)
    picked = (event.selection.objects.get("cines") or [None])[0] if event and event.selection else None
    site = next((x for x in sites if picked and x["site_id"] == picked.get("site_id")), None)
    st.markdown(f"**{T['detail']}**")
    if not site:
        st.caption(T["detail_hint"])
    else:
        table([CHAIN_LABEL[site["chain"]]] + [r["cinema_name"] for r in site["cinemas"]],
              [[MAP_METRIC[m][0]] + [cell(r, m) for r in site["cinemas"]] for m in MAP_METRIC],
              num_cols=range(1, len(site["cinemas"]) + 1))
    leerla("mapa", T["leer"])

# --- apéndice ------------------------------------------------------------------------------------------------------
with apendice("mapa-tabla", T["table"], f"{n(len(cinemas))} {COLUMN_LABEL['cinemas'].lower()}"):
    cols = ["chain", "cinema_name", "shows", "titles", "screens", "seats", "ticket_price", "ticket_sampled_at", "ticket_max",
            "ticket_max_format", "popcorn_price",
            "sold_pct", "occupancy_samples"]
    st.dataframe(pretty(cinemas[cols].assign(ticket_max_format=cinemas.ticket_max_format.map(FORMAT_LABEL))), width="stretch", hide_index=True, height=480,
                 column_config=money_config(["ticket_price", "ticket_max", "popcorn_price"]))

md(f'<p class="pie">{esc(T["footer"])}</p>')
