"""Dashboard ejecutivo del piloto CDMX: Cinemex frente a Cinépolis, en tres capas.

Capa 1, "Lo que importa hoy": hasta tres hallazgos redactados como decisión (analytics.findings).
Capa 2, "Evidencia por pregunta": cada sección abre con la conclusión y el gráfico es la prueba.
Capa 3, "Detalle y apéndice": todo colapsado con una línea de resumen visible, más el bloque
"Qué se desbloquea con tus datos", que agrupa lo que hoy requiere integración o historia.

Solo pinta lo que devuelve analytics/; sin SQL y sin nombres internos aquí (los textos salen de
analytics.labels, las frases de analytics.findings). Datos reales siempre: lo que no existe no se
muestra con cifras.

Vive en la raíz del repo a propósito: Streamlit solo recarga en caliente los módulos que están
bajo la carpeta del script, y así analytics/ y scraper/ también se recargan al editarlos.

Correr:  .venv/bin/streamlit run app.py
"""
import html
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analytics  # noqa: E402
from scraper import config  # noqa: E402
from analytics.labels import (  # noqa: E402
    AVAILABILITY_LABEL, CHAIN_COLOR, CHAIN_LABEL, COLUMN_LABEL, DAY_TYPE_LABEL, DIVERGING, FORMAT_BUCKETS, FORMAT_LABEL,
    GRAY, GRAY_DARK, GRAY_LIGHT, GRID, INK, KIND_HELP, KIND_LABEL, LANGUAGE_BUCKETS, LANGUAGE_LABEL, LINE, NEUTRAL, PAPER,
    RED, RED_RAMP, RED_SOFT, SLOT_SHORT, SLOTS, WEEKDAY_LABEL,
    date_es, range_es, range_short, time_12,
)

TTL = 60  # segundos; el scraper escribe cada 15 min
TZ = ZoneInfo("America/Mexico_City")
KINDS = ["added", "removed", "moved", "changed", "availability"]
CHAINS = ["cinemex", "cinepolis"]
CHAIN_DOMAIN = [CHAIN_LABEL[c] for c in CHAINS]
CHAIN_RANGE = [CHAIN_COLOR[c] for c in CHAINS]
FIRST_SNAPSHOT = date(2026, 9, 7)          # inicio de la historia; los paneles de tendencia dependen de ella
SHOWN_MOVIES, TOTAL_MOVIES = 8, 15         # dumbbell: las de mayor diferencia, y todas al pedirlo
FONT = "Archivo, system-ui, sans-serif"

st.set_page_config(page_title="Cartelera CDMX · Cinemex frente a Cinépolis", layout="wide")

# Tema (colores, radios, familia) en .streamlit/config.toml. Aquí lo que el tema no cubre: la fuente
# variable Archivo, el ancho de lectura, y los componentes del mockup (encabezado, rótulos de capa,
# tarjetas de hallazgo, conclusiones, apéndices colapsados y bloque de desbloqueo).
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
    for col in ("sampled_at", "detected_at"):
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


# --- barra lateral: periodo y alcance -------------------------------------------------------------------
today_s = analytics.today()
today_d = date.fromisoformat(today_s)
if not config.DB_PATH.exists():
    # Recién desplegado: el scraper aún no ha creado la base. Aviso claro en lugar del traceback.
    now = datetime.now(TZ)
    nxt = (now.replace(second=0, microsecond=0) + timedelta(minutes=15 - now.minute % 15))
    md('<div class="enc"><h1>Cartelera CDMX: <span>Cinemex</span> frente a Cinépolis</h1></div>')
    st.info(f"Aún no hay datos: la base {config.DB_PATH} no existe. El scraper corre cada 15 minutos; el siguiente snapshot "
            f"empieza a las {time_12(nxt.strftime('%H:%M'))} y tarda de 2 a 5 minutos. Para no esperar: "
            "`python3 -m scraper.run` (o `systemctl start absolut-cinema-scraper.service` en el servidor), o copia "
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
st.sidebar.caption(f"Los datos se capturan cada 15 minutos; esta página se refresca cada {TTL} segundos.")

# --- datos del encabezado ---------------------------------------------------------------------------------
health = load("snapshot_health", limit=12)
last_ok = health[health.ok == 1].groupby("chain").first()
# Una cadena está desactualizada si su intento más reciente falló o si su última captura buena
# tiene más de 45 min (el scraper corre cada 15). Fallos ya superados por una captura buena no avisan.
now_utc = datetime.now(ZoneInfo("UTC"))
stale = []
for chain, r in health.groupby("chain").first().iterrows():
    last_good = last_ok.loc[chain].taken_at if chain in last_ok.index else None
    age_min = (now_utc - datetime.fromisoformat(last_good)).total_seconds() / 60 if last_good else None
    if r.ok != 1 or age_min is None or age_min > 45:
        stale.append((CHAIN_LABEL.get(chain, chain), age_min, r.error if r.ok != 1 else None))
kp = load("kpis", d0=d0, d1=d1)
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
hallazgos = load_raw("findings", d0=d0, d1=d1)
if not hallazgos:
    st.info("Ninguna diferencia cruza el umbral de relevancia en este periodo. La evidencia completa está en la Capa 2.")
for f in hallazgos:
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

# ============ CAPA 2 ============
capa(2, "Evidencia por pregunta",
     "Cada sección abre con la conclusión; el gráfico es la prueba, no el mensaje. Las guías de lectura van colapsadas.")
concl = load_raw("conclusions", d0=d0, d1=d1, shown=SHOWN_MOVIES, total=TOTAL_MOVIES)

# --- Películas: dumbbell -------------------------------------------------------------------------------
with seccion("peliculas"):
    show_all = st.session_state.get("all_movies", False)
    pregunta("¿A qué películas les damos más pantalla que Cinépolis?", concl.get("peliculas", ""),
             None if show_all else concl.get("peliculas_note"))
    battle = load("movies_by_chain", d0=d0, d1=d1, limit=60)
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
    hm = load("heatmap_day_slot", d0=d0, d1=d1)
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
            x=alt.X("Franja:N", sort=[SLOT_SHORT[k] for k, *_ in SLOTS], title=None,
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
    mx = load("mix", d0=d0, d1=d1)
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
offered = load("offered_seats", d0=d0, d1=d1).set_index("chain")
cc = load("concentration", d0=d0, d1=d1).set_index("chain") if True else None
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
        (["Share de horario prime (vie–dom desde 6 PM)", f"{us.pct_prime:.1f} %", f"{them.pct_prime:.1f} %", pp(us.pct_prime - them.pct_prime)]
         if weekend else
         ["Share de 6 PM en adelante", f"{us.pct_evening:.1f} %", f"{them.pct_evening:.1f} %", pp(us.pct_evening - them.pct_evening)]),
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
by_kind = load("events_by_kind", since_hours=24)
ev = {(r.chain, r.kind): int(r.n) for r in by_kind.itertuples()} if not by_kind.empty else {}
g = lambda c, k: ev.get((c, k), 0)  # noqa: E731
resumen = (f"Últimas 24 h: {g('cinemex', 'added'):,} funciones nuevas nuestras vs {g('cinepolis', 'added'):,} de Cinépolis · "
           f"{g('cinemex', 'removed'):,} vs {g('cinepolis', 'removed'):,} canceladas") if ev else "Sin cambios en las últimas 24 h"
with apendice("cambios", "¿Qué cambió en la cartelera ya publicada?", resumen):
    if ev:
        table(["Cadena", "Nuevas", "Canceladas", "Horario/sala", "Idioma/formato", "Ocupación"],
              [[(CHAIN_LABEL[c], "cmx" if c == "cinemex" else "cnp")] + [f"{g(c, k):,}" for k in KINDS] for c in CHAINS],
              num_cols=(1, 2, 3, 4, 5))
    md('<p class="nota">' + " ".join(f"<b>{KIND_LABEL[k]}.</b> {KIND_HELP[k]}" for k in KINDS) +
       " Cuando una cadena publica la semana siguiente (miércoles o jueves) aparecen miles de funciones nuevas de golpe; "
       "eso es publicación, no cambios sobre lo ya anunciado.</p>")
    kinds = st.multiselect("Registro por función", KINDS, default=KINDS[:4], format_func=lambda k: KIND_LABEL[k])
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
        bt = load("offered_by_title", d0=d0, d1=d1, limit=TOTAL_MOVIES, chain=chain_sel)
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

# --- Ocupación muestreada -----------------------------------------------------------------------------
occ = load("occupancy_summary")
cal = load("semaphore_calibration", chain="cinemex")
n_samples = int(occ.samples.sum()) if not occ.empty else 0
weighted = 100.0 * occ.sold.sum() / occ.seats.sum() if n_samples and occ.seats.sum() else 0.0
levels = int((occ.availability != "(sin color)").sum()) if n_samples else 0
resumen = (f"{n_samples} muestras Cinépolis · {weighted:.1f} % vendido en promedio · "
           + (f"{levels} niveles de color para calibrar" if levels else "aún sin semáforos de color para calibrar")
           + (" · semáforo de Cinemex calibrado" if not cal.empty else " · semáforo de Cinemex sin calibrar"))
with apendice("ocupacion", "Ocupación muestreada a 60 min de la función", resumen):
    if n_samples == 0:
        st.info("Aún no hay muestras. El muestreo corre cada 15 minutos sobre las funciones de Cinépolis que empiezan en una hora.")
    else:
        st.markdown(f"**Cinépolis.** {n_samples} funciones muestreadas; {weighted:.1f} % de las butacas vendidas a una hora de empezar. "
                    "La tabla cruza el color del semáforo del sitio con el porcentaje real vendido, para calibrar qué significa cada color.")
        st.dataframe(pretty(occ[["availability", "samples", "avg_sold_pct", "min_sold_pct", "max_sold_pct"]]), width="stretch", hide_index=True)
    if cal.empty:
        st.markdown("**Cinemex.** Publica alta, media o baja disponibilidad por función. Al calibrar cada nivel contra planos reales "
                    "(una pasada única, por la tarde-noche, cuando existen los tres niveles) el semáforo se convierte en % vendido "
                    "estimado para todas sus funciones.")
    else:
        est = load("estimated_occupancy", d0=d0, d1=d1, chain="cinemex")
        if not est.empty and has(est.iloc[0].seats_occupied_est):
            e = est.iloc[0]
            st.markdown(f"**Cinemex.** {int(e.seats_occupied_est):,} butacas ocupadas estimadas de {int(e.seats_offered):,} ofertadas en el "
                        f"periodo ({e.occupancy_pct_est:.1f} %), a partir del nivel de disponibilidad de cada función y su calibración "
                        f"({int(e.shows_estimated):,} de {int(e.shows):,} funciones estimables).")
        st.dataframe(pretty(cal.rename(columns={"level": "availability"})[["availability", "samples", "sold_pct", "min_sold_pct", "max_sold_pct"]]),
                     width="stretch", hide_index=True)
    if n_samples:
        st.markdown("**Últimas muestras (Cinépolis)**")
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

md(f'<p class="pie">Fuentes: cartelera pública de Cinemex y Cinépolis, capturada cada 15 minutos para los cines de la Ciudad de México '
   f'y área metropolitana; aforo por sala de ambas cadenas leído de los planos de asientos; ocupación muestreada a 60 minutos de cada '
   f'función en Cinépolis; precios de lista muestreados por cine, formato y tipo de día. Las películas se emparejan por título hasta '
   f'contar con la tabla de equivalencias entre cadenas. Historia desde el {esc(date_es(FIRST_SNAPSHOT.isoformat()))}.</p>')
