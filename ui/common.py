"""Herramientas compartidas por las páginas del dashboard (`views/`): constantes, carga cacheada de
`analytics/`, formato, componentes del mockup (rótulos de capa, secciones, tarjetas de hallazgo, apéndices,
tablas y gráficas) y el CSS.

Las páginas hacen `from ui.common import *`: comparten un solo espacio de nombres a propósito, porque son la
capa de presentación de un mismo tablero y así se leen igual que cuando todo vivía en `app.py`.
Solo pinta lo que devuelve analytics/; sin SQL y sin nombres internos aquí (los textos salen de analytics.labels,
las frases de analytics.findings).
"""
import html
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analytics  # noqa: E402
from scraper import config  # noqa: E402
from scraper.health import MAX_AGE_MIN  # noqa: E402  (umbral de captura vieja, el mismo que scraper.health)
from analytics.labels import (  # noqa: E402
    CINEMA_TYPE_LABEL, FIELD_LABEL, FULL_DAY, HOUR_MARKS, HOUR_PRESETS, PLATFORM_LABEL, STATUS_LABEL, VS_NOW_LABEL,
    hour_mark, hours_label,
    AVAILABILITY_LABEL, CHAIN_COLOR, CHAIN_LABEL, COLUMN_LABEL, DAY_TYPE_LABEL, DIVERGING, FORMAT_BUCKETS, FORMAT_LABEL,
    GRAY, GRAY_DARK, GRAY_LIGHT, GRID, INK, KIND_HELP, KIND_LABEL, LANGUAGE_BUCKETS, LANGUAGE_LABEL, LINE, NEUTRAL, PAPER,
    RED, RED_RAMP, RED_SOFT, SLOT_SHORT, SLOTS, WEEKDAY_LABEL,
    date_es, range_es, range_short, time_12,
)

TTL = 60  # segundos; los planos de asientos escriben cada 15 min y la cartelera tres veces al día
TZ = ZoneInfo("America/Mexico_City")
KINDS = ["added", "removed", "moved", "changed", "availability"]
CHAINS = ["cinemex", "cinepolis"]
CHAIN_DOMAIN = [CHAIN_LABEL[c] for c in CHAINS]
CHAIN_RANGE = [CHAIN_COLOR[c] for c in CHAINS]
FIRST_SNAPSHOT = date(2026, 9, 7)          # inicio de la historia; los paneles de tendencia dependen de ella
SHOWN_MOVIES, TOTAL_MOVIES = 8, 15         # dumbbell: las de mayor diferencia, y todas al pedirlo
FONT = "Archivo, system-ui, sans-serif"

PAGE_TITLE = "Cartelera CDMX · Cinemex frente a Cinépolis"

def inject_css():
    """Tema (colores, radios, familia) en .streamlit/config.toml. Aquí lo que el tema no cubre: la fuente variable
    Archivo, el ancho de lectura y los componentes del mockup (encabezado, rótulos de capa, tarjetas de hallazgo,
    conclusiones, apéndices colapsados y bloque de desbloqueo). Se llama en cada corrida desde app.py."""
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:ital,wdth,wght@0,62..125,400..900;1,62..125,400..900&display=swap');
.block-container {{ max-width: 1120px; padding-top: 2.4rem; padding-bottom: 5rem; }}
h1, h2, h3 {{ letter-spacing: -.005em; }}

/* encabezado */
.enc {{ padding: 6px 0 8px; border-bottom: 3px solid {INK}; margin-bottom: 8px; }}
.enc h1 {{ font-size: clamp(30px, 4.2vw, 46px); font-weight: 850; font-stretch: 75%; line-height: 1.02; margin: 0; padding: 0; }}
.enc h1 span {{ color: {RED}; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 6px 22px; padding: 12px 0 14px; color: {GRAY}; font-size: 13.5px; }}
.meta strong {{ color: {INK}; font-weight: 600; }}
.nav-capas {{ display: flex; border: 1.5px solid {INK}; border-radius: 999px; width: max-content; margin: 14px 0 22px;
              overflow: hidden; font-size: 13px; font-weight: 600; }}
.nav-capas a {{ color: {INK}; text-decoration: none; padding: 7px 18px; border-right: 1.5px solid {INK}; }}
.nav-capas a:last-child {{ border-right: none; }}
.nav-capas a:hover {{ background: {RED_SOFT}; }}
.nav-capas a b {{ color: {RED}; margin-right: 6px; }}

/* rótulos de capa */
.capa-tag {{ display: flex; align-items: baseline; gap: 14px; margin: 44px 0 4px; }}
.capa-tag .num {{ font-weight: 850; font-stretch: 70%; font-size: 15px; color: #fff; background: {INK}; padding: 3px 12px;
                  border-radius: 4px; white-space: nowrap; }}
.capa-tag .num.roja {{ background: {RED}; }}
.capa-tag h2 {{ font-weight: 800; font-stretch: 80%; font-size: 26px; margin: 0; padding: 0; }}
.capa-desc {{ color: {GRAY}; font-size: 13.5px; margin: 2px 0 18px; max-width: 640px; }}

/* Capa 1: hallazgos */
.hallazgo {{ background: {PAPER}; border: 1px solid {LINE}; border-left: 5px solid {RED}; border-radius: 6px; padding: 20px 24px;
             display: grid; grid-template-columns: 1fr 240px; gap: 24px; align-items: center; margin-bottom: 14px; }}
.hallazgo h3 {{ font-size: 19px; font-weight: 750; line-height: 1.28; margin: 0 0 6px; padding: 0; }}
.hallazgo p {{ color: {GRAY}; font-size: 13.5px; margin: 0; }}
.hallazgo .accion {{ display: inline-block; margin-top: 10px; font-size: 12.5px; font-weight: 700; color: {RED}; background: {RED_SOFT};
                     padding: 3px 10px; border-radius: 4px; }}
.soporte {{ border-left: 1px solid {LINE}; padding-left: 22px; }}
.soporte .par {{ display: flex; justify-content: space-between; gap: 10px; font-size: 13px; padding: 3px 0; color: {GRAY}; }}
.soporte .par b {{ color: {INK}; font-weight: 750; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.soporte .par .cmx {{ color: {RED}; }}

/* Capa 2: secciones */
[class*="st-key-sec-"] {{ background: {PAPER}; border: 1px solid {LINE} !important; border-radius: 6px; padding: 22px 26px 18px; margin-bottom: 18px; }}
.pregunta {{ font-weight: 800; font-stretch: 82%; font-size: 22px; margin: 0 0 4px; padding: 0; line-height: 1.2; }}
.conclusion {{ font-weight: 700; font-size: 15.5px; margin: 6px 0 14px; padding: 10px 14px; background: {GRAY_LIGHT}; border-radius: 5px;
               border-left: 3px solid {INK}; line-height: 1.45; }}
.conclusion em {{ font-style: italic; font-weight: 500; color: {GRAY}; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 18px; font-size: 12.5px; color: {GRAY}; margin: 0 0 4px; }}
.leyenda i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }}
.leyenda i.sq {{ border-radius: 2px; width: 9px; height: 9px; }}
[class*="st-key-leerla-"] [data-testid="stExpander"] details {{ border: none !important; background: transparent !important; }}
[class*="st-key-leerla-"] [data-testid="stExpander"] summary {{ padding: 2px 0 !important; font-size: 13px; font-weight: 600; width: max-content; }}
[class*="st-key-leerla-"] [data-testid="stExpander"] summary:hover {{ color: {RED} !important; }}
[class*="st-key-leerla-"] [data-testid="stExpander"] p {{ font-size: 13px; color: {GRAY}; max-width: 720px; }}

/* Capa 3: apéndices */
[class*="st-key-apendice-"] [data-testid="stExpander"] details {{ background: {PAPER}; border: 1px solid {LINE} !important; border-radius: 6px; }}
[class*="st-key-apendice-"] [data-testid="stExpander"] summary {{ padding: 14px 22px !important; font-weight: 700; font-size: 15px; }}
[class*="st-key-apendice-"] [data-testid="stExpander"] summary svg {{ color: {RED}; }}
[class*="st-key-apendice-"] {{ margin-bottom: 4px; }}
table.mk {{ border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; margin: 4px 0 10px; }}
table.mk th {{ text-align: left; font-weight: 600; color: {GRAY}; border-bottom: 1.5px solid {LINE}; padding: 7px 10px; }}
table.mk td {{ border: none; border-bottom: 1px solid {LINE}; padding: 7px 10px; color: {INK}; }}
table.mk th {{ border-left: none; border-right: none; border-top: none; }}
table.mk td.num, table.mk th.num {{ text-align: right; }}
table.mk .cmx {{ color: {RED}; font-weight: 700; }}
table.mk .cnp {{ font-weight: 700; }}
table.mk td.sum {{ font-weight: 700; border-top: 2px solid {LINE}; background: {GRAY_LIGHT}; }}
.nota {{ color: {GRAY}; font-size: 13px; margin: 6px 0 2px; }}

/* desbloqueo */
.desbloqueo {{ background: {INK}; color: #fff; border-radius: 8px; padding: 28px 30px; margin-top: 26px; }}
.desbloqueo h3 {{ font-weight: 800; font-stretch: 82%; font-size: 22px; margin: 0 0 4px; padding: 0; color: #fff; }}
.desbloqueo > p {{ color: #B9BCC4; font-size: 13.5px; max-width: 640px; margin: 0 0 18px; }}
.desb-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }}
.desb-item {{ background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14); border-radius: 6px; padding: 14px 16px; }}
.desb-item .cuando {{ font-size: 11.5px; font-weight: 700; color: #FF7A90; margin-bottom: 5px; }}
.desb-item .que {{ font-size: 14px; font-weight: 650; line-height: 1.3; margin-bottom: 5px; }}
.desb-item p {{ font-size: 12.5px; color: #A7ABB5; line-height: 1.45; margin: 0; }}
.pie {{ margin-top: 48px; padding-top: 16px; border-top: 1px dashed {LINE}; color: {GRAY}; font-size: 12.5px; }}

/* controles */
.stButton > button, [data-testid="stBaseButton-secondary"] {{ font-weight: 600; border: 1.5px solid {INK}; color: {INK}; }}
.stButton > button:hover {{ background: {RED_SOFT}; border-color: {INK}; color: {INK}; }}
@media (max-width: 760px) {{
  .hallazgo {{ grid-template-columns: 1fr; }}
  .soporte {{ border-left: none; padding-left: 0; border-top: 1px solid {LINE}; padding-top: 12px; }}
}}

/* Navegación entre páginas: barra superior en escritorio; en celular se fija al pie de la pantalla. */
[data-testid="stTopNavLink"] {{ font-family: {FONT}; font-weight: 600; }}
@media (max-width: 768px) {{
  [data-testid="stTopNavSection"] {{ position: fixed; left: 0; right: 0; bottom: 0; top: auto; z-index: 1000;
    display: flex; justify-content: space-around; align-items: center; padding: 8px 0 12px;
    background: {PAPER}; border-top: 1px solid {LINE}; box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06); }}
  [data-testid="stTopNavLink"] {{ font-size: 15px; }}
  .block-container {{ padding-bottom: 84px; }}
}}
</style>
""", unsafe_allow_html=True)


# --- utilidades ------------------------------------------------------------------------------------
@st.cache_data(ttl=TTL)
def load(fn_name, **kwargs):
    conn = analytics.connect()
    try:
        return pd.DataFrame(getattr(analytics, fn_name)(conn, **kwargs))
    finally:
        conn.close()


@st.cache_data(ttl=TTL)
def load_raw(fn_name, **kwargs):
    """Para funciones que devuelven listas de dicts anidados o dicts (findings, conclusions)."""
    conn = analytics.connect()
    try:
        return getattr(analytics, fn_name)(conn, **kwargs)
    finally:
        conn.close()


def esc(s):
    return html.escape(str(s))


def md(s):
    """HTML crudo sin líneas en blanco (markdown cortaría el bloque)."""
    st.markdown("\n".join(line for line in s.splitlines() if line.strip()), unsafe_allow_html=True)


def n(v, nd=0):
    return "—" if v is None or pd.isna(v) else f"{float(v):,.{nd}f}"


def pp(v):
    return f"{v:+.1f} pp".replace("-", "−")


def local_time(iso):
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d/%m %I:%M %p").lstrip("0")


def pretty(df, index=None):
    """Etiquetas en español para cadena, tipo de cambio, columnas y horas."""
    df = df.copy()
    if "chain" in df.columns:
        df["chain"] = df["chain"].map(CHAIN_LABEL).fillna(df["chain"])
    if "kind" in df.columns:
        df["kind"] = df["kind"].map(KIND_LABEL).fillna(df["kind"])
    if "format_bucket" in df.columns:
        df["format_bucket"] = df["format_bucket"].map(FORMAT_LABEL).fillna(df["format_bucket"])
    if "day_type" in df.columns:
        df["day_type"] = df["day_type"].map(DAY_TYPE_LABEL).fillna(df["day_type"])
    if "availability" in df.columns:
        df["availability"] = df["availability"].fillna("(sin color)").replace("", "(sin color)").map(
            lambda v: AVAILABILITY_LABEL.get(v, v))
    if "status" in df.columns:
        df["status"] = df["status"].map(STATUS_LABEL).fillna(df["status"])
    if "vs_now" in df.columns:
        df["vs_now"] = df["vs_now"].map(VS_NOW_LABEL).fillna(df["vs_now"])
    for col in ("sampled_at", "detected_at", "first_seen"):
        if col in df.columns:
            df[col] = df[col].map(lambda s: local_time(s) if isinstance(s, str) else s)
    if "datetime_local" in df.columns:
        df["datetime_local"] = df["datetime_local"].map(
            lambda s: f"{date_es(s[:10])}, {time_12(s[11:16])}" if isinstance(s, str) and len(s) >= 16 else s)
    df = df.rename(columns=COLUMN_LABEL)
    if index:
        df = df.set_index(COLUMN_LABEL.get(index, index))
    return df


def has(v):
    """Valor numérico presente y mayor que cero (los LEFT JOIN dejan NaN)."""
    return v is not None and pd.notna(v) and float(v) > 0


def table(headers, rows, num_cols=()):
    """Tabla HTML compacta al estilo del mockup. `rows` son listas de celdas ya formateadas; una celda
    puede ser (texto, clase)."""
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = []
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            txt, cls = (c if isinstance(c, tuple) else (c, ""))
            cls = " ".join(x for x in (cls, "num" if i in num_cols else "") if x)
            tds.append(f'<td class="{cls}">{esc(txt)}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    md(f'<table class="mk"><tr>{th}</tr>{"".join(body)}</table>')


def chart(c, width="stretch"):
    """Estilo común de las gráficas: fuente, rejilla tenue, sin marco."""
    c = (c.configure(font=FONT, background=PAPER)
          .configure_view(strokeWidth=0)
          .configure_axis(labelColor=GRAY, titleColor=GRAY, gridColor=GRID, domainColor=LINE, tickColor=LINE,
                          labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
          .configure_legend(labelColor=GRAY, labelFontSize=12.5, symbolSize=70))
    st.altair_chart(c, width=width)


def capa(num, title, desc, roja=False, anchor=None):
    md(f'<div class="capa-tag" id="{anchor or f"capa{num}"}"><span class="num{" roja" if roja else ""}">CAPA {num}</span>'
       f'<h2>{esc(title)}</h2></div><p class="capa-desc">{esc(desc)}</p>')


def seccion(slug):
    return st.container(key=f"sec-{slug}")


def pregunta(texto, conclusion, nota=None):
    md(f'<h3 class="pregunta">{esc(texto)}</h3>'
       f'<p class="conclusion">{esc(conclusion)}{f" <em>{esc(nota)}</em>" if nota else ""}</p>')


def leerla(slug, texto):
    with st.container(key=f"leerla-{slug}"):
        with st.expander("Cómo leerla"):
            st.markdown(texto)


def apendice(slug, title, resumen):
    """Expander con línea de resumen visible: quien lo necesita lo abre."""
    label = f"{title}  :gray[· {resumen}]".replace("$", "\\$") if resumen else title   # $ escapado: si no, LaTeX
    return st.container(key=f"apendice-{slug}").expander(label)


def leyenda(items, square=False):
    md('<div class="leyenda">' + "".join(
        f'<span><i class="{"sq" if square else ""}" style="background:{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>")



def hallazgo(f):
    """Tarjeta de hallazgo de la Capa 1: titular como decisión, contexto, chip de decisión y números de soporte."""
    soporte = "".join(
        f'<div class="par"><span>{esc(s["label"])}</span><b class="{"cmx" if s["cmx"] else ""}">{esc(s["value"])}</b></div>'
        for s in f["support"])
    md(f"""
<div class="hallazgo">
  <div>
    <h3>{esc(f["title"])}</h3>
    <p>{esc(f["body"])}</p>
    <span class="accion">{esc(f["action"])}</span>
  </div>
  <div class="soporte">{soporte}</div>
</div>
""")
