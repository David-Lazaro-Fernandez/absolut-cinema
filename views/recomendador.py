"""Página del recomendador: el usuario dice desde dónde sale (dirección, su ubicación o un clic en el mapa), quiénes van
(adultos, niños, adultos mayores), qué dulcería quieren, cuánto quieren gastar en total y cuándo, y ve las funciones de
las tres cadenas que le quedan cerca y caben en el presupuesto. El cálculo vive en `analytics/recommender.py`; aquí
solo se toman los datos y se pinta. El mapa es Leaflet (`streamlit-folium`) porque necesita la coordenada de un clic
en cualquier punto, y pydeck solo avisa de clics sobre un objeto."""
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

from ui.common import *  # noqa: F401,F403

T = RECOMMEND_TEXT
_CDMX_CENTER = (19.4326, -99.1332)        # Zócalo: el mapa abre aquí hasta que hay un punto de partida
_DAYS_AHEAD = 13                           # las cadenas publican hasta el miércoles de la semana siguiente
_PER_CINEMA, _LIMIT = 3, 40
_MARKER_RADIUS = 7

if not config.DB_PATH.exists():
    st.info(T["no_db"])
    st.stop()


def set_location(lat, lng, source):
    st.session_state["rec_location"] = (round(lat, 5), round(lng, 5))
    st.session_state["rec_source"] = source


def group_text(counts):
    parts = [f"{k} {GROUP_LABEL[g][0 if k == 1 else 1]}" for g, k in counts.items() if k]
    return " y ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else parts[0]


def money(v):
    return f"${v:,.0f}"


def when_text(r):
    hhmm = time_12(r.datetime_local[11:16])
    return hhmm if r.date == analytics.today() else f"{date_es(r.date, with_year=False)}, {hhmm}"


def snack_cell(r, snacks):
    """Dulcería del paquete elegido; sin paquete, la referencia de palomitas y refresco donde el cine publica su menú."""
    if snacks != "none":
        return money(r.snacks_total)
    return T["snack_reference"].format(price=money(r.snack_reference)) if has(r.snack_reference) else T["snack_no_menu"]


def cinema_cell(r):
    return f"{r.cinema_name} · {CHAIN_LABEL[r.chain]}", "cmx" if r.chain == "cinemex" else ""


md(f'<div class="enc"><h1>{T["title"]}</h1></div>')

# --- tu plan: desde dónde, quiénes, cuánto y cuándo ------------------------------------------------------------------
with seccion("rec-plan"):
    pregunta(T["plan"], T["plan_desc"])
    with st.form("rec_address", border=False):
        a1, a2 = st.columns([5, 1], vertical_alignment="bottom")
        address = a1.text_input(T["address"], placeholder=T["address_placeholder"], key="rec_address_text")
        if a2.form_submit_button(T["search"], width="stretch") and address.strip():
            found = load_geocode(address.strip())
            if found is None:
                st.warning(T["not_found"])
            elif "error" in found:
                st.warning(T["geocoder_down"])
            else:
                set_location(found["lat"], found["lng"], found["label"])
    if st.button(T["locate"], icon=":material/my_location:", key="rec_locate"):
        st.session_state["rec_geo_asked"] = True
    if st.session_state.get("rec_geo_asked"):
        device = get_geolocation(component_key="rec_geo")
        if device is None:
            st.caption(T["locating"] + " " + T["locate_https"])
        else:
            st.session_state["rec_geo_asked"] = False
            coords = device.get("coords") if isinstance(device, dict) else None
            if coords:
                set_location(coords["latitude"], coords["longitude"], "device")
            else:
                st.warning(T["locate_denied"])

    g1, g2, g3, g4 = st.columns(4)
    group = {"adults": g1.number_input(T["adults"], min_value=0, max_value=10, value=2, key="rec_adults"),
             "children": g2.number_input(T["children"], min_value=0, max_value=10, value=0, key="rec_children"),
             "seniors": g3.number_input(T["seniors"], min_value=0, max_value=10, value=0, key="rec_seniors")}
    budget = g4.number_input(T["budget"], min_value=0, max_value=20000, value=0, step=100, key="rec_budget", help=T["budget_help"])
    s1, s2 = st.columns([3, 2])
    snacks = s1.radio(T["snacks"], list(SNACK_LABEL), format_func=SNACK_LABEL.get, horizontal=True, key="rec_snacks")
    today_d = date.fromisoformat(analytics.today())
    when = s2.radio(T["when"], [T["today"], T["tomorrow"], T["pick"]], horizontal=True, key="rec_when")
    day = {T["today"]: today_d, T["tomorrow"]: today_d + timedelta(days=1)}.get(when)
    if day is None:
        day = s2.date_input(T["date"], value=today_d, min_value=today_d, max_value=today_d + timedelta(days=_DAYS_AHEAD),
                            format="DD/MM/YYYY", key="rec_date")

# El clic del mapa llega en la recarga siguiente: se lee del estado del componente y solo cuenta si es un clic nuevo.
clicked = (st.session_state.get("rec_map") or {}).get("last_clicked")
if clicked and clicked != st.session_state.get("rec_click_seen"):
    st.session_state["rec_click_seen"] = clicked
    set_location(clicked["lat"], clicked["lng"], "click")
location = st.session_state.get("rec_location")
d0 = d1 = day.isoformat()

with st.expander(T["more"]):
    m1, m2, m3 = st.columns(3)
    preset = m1.radio(T["hours"], list(HOUR_PRESETS), key="rec_hours")
    radius_km = m2.slider(T["radius"], min_value=1, max_value=20, value=5, key="rec_radius")
    sort = m3.radio(T["sort"], list(RECOMMEND_SORT), format_func=RECOMMEND_SORT.get, key="rec_sort")
    hours = tuple(HOUR_PRESETS[preset])
    area = dict(d0=d0, d1=d1, hours=hours, radius_km=float(radius_km))
    title_norm, formats = None, None
    if location:
        titles = load("recommend_titles", lat=location[0], lng=location[1], **area)
        names = dict(zip(titles.title_norm, titles.title)) if not titles.empty else {}
        f1, f2 = st.columns(2)
        title_norm = f1.selectbox(T["title_filter"], [None, *names], format_func=lambda t: T["any_title"] if t is None else names[t],
                                  key="rec_title")
        formats = tuple(f2.multiselect(T["formats"], FORMAT_BUCKETS, format_func=FORMAT_LABEL.get, placeholder=T["any_format"],
                                       key="rec_formats")) or None

source = st.session_state.get("rec_source")
if location:
    st.caption(T["from_click"] if source == "click" else T["from_device"] if source == "device" else T["found"].format(label=source))

# --- mapa ------------------------------------------------------------------------------------------------------------
filters = dict(**{k: int(v) for k, v in group.items()}, snacks=snacks, budget=float(budget) or None, title_norm=title_norm,
               formats=formats, **area)
people = sum(filters[k] for k in group)
ready = location and people
results = load("recommend", lat=location[0], lng=location[1], sort=sort, per_cinema=_PER_CINEMA, limit=_LIMIT, **filters) \
    if ready else pd.DataFrame()

with seccion("rec-mapa"):
    pregunta(T["map"], T["map_desc"])
    leyenda([(CHAIN_LABEL[c], CHAIN_COLOR[c]) for c in CHAIN_LABEL])
    fmap = vector_basemap(folium.Map(location=location or _CDMX_CENTER, zoom_start=13 if location else 11, tiles=None))
    if location:
        folium.CircleMarker(location, radius=_MARKER_RADIUS + 2, color=INK, weight=3, fill=True, fill_color=PAPER,
                            fill_opacity=1, tooltip=T["start"]).add_to(fmap)
        folium.Circle(location, radius=radius_km * 1000, color=GRAY, weight=1, fill=False).add_to(fmap)
        for r in (results.drop_duplicates(["chain", "cinema_id"]).itertuples() if not results.empty else []):
            folium.CircleMarker((r.lat, r.lng), radius=_MARKER_RADIUS, color=PAPER, weight=1, fill=True,
                                fill_color=CHAIN_COLOR[r.chain], fill_opacity=0.9,
                                tooltip=esc(f"{r.cinema_name} · {CHAIN_LABEL[r.chain]}")).add_to(fmap)
    st_folium(fmap, key="rec_map", height=420, use_container_width=True, returned_objects=["last_clicked"])

if not location:
    st.info(T["no_location"])
    st.stop()
if not people:
    st.info(T["group_empty"])
    st.stop()

# --- resultados --------------------------------------------------------------------------------------------------------
with seccion("rec-resultados"):
    summary = load_raw("recommend_summary", lat=location[0], lng=location[1], **filters)
    if not summary["shows"]:
        pregunta(T["results"], T["none"])
    else:
        c, near = summary["cheapest"], summary["nearest"]
        head = T["summary_budget"] if filters["budget"] else T["summary_open"]
        text = head.format(group=group_text(group), shows=n(summary["shows"]), cinemas=n(summary["cinemas"]),
                           snacks=SNACK_LABEL[snacks].lower())
        text += T["summary_best"].format(cheapest=c["cinema_name"], cheapest_total=money(c["total"]),
                                         cheapest_km=T["km"].format(km=c["distance_km"]), nearest=near["cinema_name"],
                                         nearest_km=T["km"].format(km=near["distance_km"]))
        if summary["saving"]:
            text += T["summary_saving"].format(saving=money(summary["saving"]))
        pregunta(T["results"], text, T["per_cinema_note"].format(n=_PER_CINEMA))
        table([T["col_cinema"], T["col_title"], T["col_time"], T["col_format"], T["col_language"], T["col_tickets"],
               T["col_snacks"], T["col_total"], T["col_distance"]],
              [[cinema_cell(r), r.title, when_text(r), FORMAT_LABEL.get(r.format_bucket, r.format_bucket),
                LANGUAGE_LABEL.get(r.language, r.language), money(r.tickets_total),
                snack_cell(r, snacks), money(r.total), T["km"].format(km=r.distance_km)]
               for r in results.itertuples()],
              num_cols=(5, 6, 7, 8))
    leerla("recomendador", T["leer"])

if snacks != "none" and summary["snacks_unpriced"]:
    partial = load("recommend", lat=location[0], lng=location[1], status="snacks_unpriced", sort=sort, per_cinema=_PER_CINEMA,
                   limit=_LIMIT, **filters)
    with seccion("rec-sin-dulceria"):
        pregunta(T["snacks_unpriced"], T["snacks_unpriced_desc"])
        table([T["col_cinema"], T["col_title"], T["col_time"], T["col_format"], T["col_tickets"], T["col_distance"]],
              [[cinema_cell(r), r.title, when_text(r), FORMAT_LABEL.get(r.format_bucket, r.format_bucket),
                money(r.tickets_total), T["km"].format(km=r.distance_km)] for r in partial.itertuples()],
              num_cols=(4, 5))

unpriced = load("recommend", lat=location[0], lng=location[1], status="unpriced", sort="distance", limit=_LIMIT, **filters)
with apendice("rec-sin-precio", T["unpriced"], T["unpriced_summary"].format(n=n(summary["unpriced"]))):
    st.caption(T["unpriced_desc"])
    if not unpriced.empty:
        table([T["col_cinema"], T["col_title"], T["col_time"], T["col_distance"]],
              [[cinema_cell(r)[0], r.title, when_text(r), T["km"].format(km=r.distance_km)] for r in unpriced.itertuples()],
              num_cols=(3,))

md(f'<p class="pie">{esc(T["footer"])}</p>')
