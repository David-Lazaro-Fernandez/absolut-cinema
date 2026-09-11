"""Explorador de datos: las tablas curadas del archivo histórico (Postgres) con filtros en la barra lateral,
orden y búsqueda de la propia tabla, y descarga en CSV. La consulta vive en `archive/`; aquí solo se arman los
controles que declara `archive.DATASETS` para cada conjunto y se pinta el resultado."""
from ui.common import *  # noqa: F401,F403

md(f"""
<div class="enc">
  <h1>{esc(DATA_TEXT["title"])}</h1>
  <div class="meta"><span>{esc(DATA_TEXT["lead"])}</span></div>
</div>
""")

st.sidebar.header(DATA_TEXT["dataset"])
key = st.sidebar.selectbox(DATA_TEXT["dataset"], options=list(archive.DATASETS), format_func=DATASET_LABEL.get,
                           key="dataset", label_visibility="collapsed")
filters = archive.DATASETS[key]["filters"]
st.caption(DATASET_HELP[key])

try:
    kwargs = {}
    if "dates" in filters:
        w0, w1 = analytics.cinema_week(analytics.today())
        picked = st.sidebar.date_input(DATA_TEXT["dates"], value=(date.fromisoformat(w0), date.fromisoformat(w1)), key="dates")
        if isinstance(picked, tuple) and len(picked) == 2:
            kwargs["d0"], kwargs["d1"] = picked[0].isoformat(), picked[1].isoformat()
        else:
            st.stop()  # rango a medio elegir
    if "platform" in filters:
        plat = st.sidebar.selectbox(DATA_TEXT["platform"], options=[None, *PLATFORM_LABEL],
                                    format_func=lambda v: DATA_TEXT["all"] if v is None else PLATFORM_LABEL[v], key="platform")
        kwargs["platform"] = plat
    if "chain" in filters:
        chain = st.sidebar.radio(DATA_TEXT["chain"], options=[None, *CHAINS],
                                 format_func=lambda v: DATA_TEXT["both"] if v is None else CHAIN_LABEL[v], horizontal=True, key="chain")
        kwargs["chain"] = chain
    if "cinema_ids" in filters:
        opts = load_pg("cinema_options", chain=kwargs.get("chain"))
        names = {r.cinema_id: (r.cinema_name if kwargs.get("chain") else f"{CHAIN_LABEL[r.chain]} · {r.cinema_name}")
                 for r in opts.itertuples()} if not opts.empty else {}
        chosen = st.sidebar.multiselect(DATA_TEXT["cinemas"], options=list(names), format_func=names.get, key="cinema_ids")
        kwargs["cinema_ids"] = tuple(chosen) or None
    if "format_bucket" in filters:
        kwargs["format_bucket"] = st.sidebar.selectbox(DATA_TEXT["format"], options=[None, *FORMAT_BUCKETS],
                                                       format_func=lambda v: DATA_TEXT["all"] if v is None else FORMAT_LABEL[v], key="format_bucket")
    if "day_type" in filters:
        kwargs["day_type"] = st.sidebar.selectbox(DATA_TEXT["day_type"], options=[None, *DAY_TYPE_LABEL],
                                                  format_func=lambda v: DATA_TEXT["all"] if v is None else DAY_TYPE_LABEL[v], key="day_type")
    if "category" in filters:
        cats = load_pg("categories", dataset=key)
        cat_list = cats.iloc[:, 0].tolist() if not cats.empty else []
        kwargs["category"] = st.sidebar.selectbox(DATA_TEXT["category"], options=[None, *cat_list],
                                                  format_func=lambda v: DATA_TEXT["all"] if v is None else v, key=f"category_{key}")
    if "search" in filters:
        kwargs["search"] = st.sidebar.text_input(DATA_TEXT["search"], help=DATA_TEXT["search_help"], key=f"search_{key}") or None
    if "only_open" in filters:
        kwargs["only_open"] = st.sidebar.checkbox(DATA_TEXT["only_open"], value=False, key="only_open")
    if "latest_only" in filters:
        kwargs["latest_only"] = st.sidebar.checkbox(DATA_TEXT["latest_only"], value=True, key=f"latest_{key}")

    df = load_pg(key, **kwargs)
except PG_ERROR:
    st.info(AUTH_TEXT["pg_unavailable"])
    st.stop()

if df.empty:
    st.info(DATA_TEXT["empty"])
    st.stop()

if len(df) >= archive.MAX_ROWS:
    st.warning(DATA_TEXT["truncated"].format(n=f"{archive.MAX_ROWS:,}"))
else:
    st.caption(DATA_TEXT["rows"].format(n=f"{len(df):,}"))

price_cols = [c for c in ("general_price", "min_price", "max_price", "fee_price", "price") if c in df.columns]
shown = pretty(df.drop(columns=[c for c in ("cinema_id", "show_id", "lat", "lng") if c in df.columns]))
st.dataframe(shown, width="stretch", hide_index=True, height=560, column_config=money_config(price_cols))
suffix = f"_{kwargs['d0']}_{kwargs['d1']}" if "d0" in kwargs else ""
st.download_button(DATA_TEXT["download"], shown.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"{key}{suffix}.csv", mime="text/csv", key="download")
