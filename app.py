"""Dashboard ejecutivo del piloto CDMX: Cinemex frente a Cinépolis.

Solo pinta lo que devuelve analytics/; sin SQL y sin nombres internos aquí (los textos salen de
analytics.labels y las frases de analytics.headlines). Orden de paneles según el brief ejecutivo:
cada panel abre con la pregunta de negocio que responde. Los paneles cuyos datos aún no existen
se muestran marcados como pendientes, nunca con cifras inventadas.

Vive en la raíz del repo a propósito: Streamlit solo recarga en caliente los módulos que están
bajo la carpeta del script, y así analytics/ y scraper/ también se recargan al editarlos.

Correr:  .venv/bin/streamlit run app.py
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analytics  # noqa: E402
from analytics.labels import (  # noqa: E402
    AVAILABILITY_LABEL, CHAIN_COLOR, CHAIN_LABEL, COLUMN_LABEL, DAY_TYPE_LABEL, DIVERGING, FORMAT_BUCKETS, FORMAT_LABEL, GRAY_DARK,
    KIND_HELP, KIND_LABEL, LANGUAGE_BUCKETS, LANGUAGE_LABEL, NEUTRAL, PRIME_LABEL, RED, RED_DARK, RED_RAMP, SLOT_LABEL,
    SLOT_SHORT, SLOTS, WEEKDAY_LABEL,
    date_es, range_es, time_12,
)

TTL = 60  # segundos; el scraper escribe cada 15 min
TZ = ZoneInfo("America/Mexico_City")
KINDS = ["added", "removed", "moved", "changed", "availability"]
CHAINS = ["cinemex", "cinepolis"]
CHAIN_DOMAIN = [CHAIN_LABEL[c] for c in CHAINS]
CHAIN_RANGE = [CHAIN_COLOR[c] for c in CHAINS]
FIRST_SNAPSHOT = date(2026, 9, 7)          # inicio de la historia; los paneles de tendencia dependen de ella
WHITE = "#FFFFFF"

st.set_page_config(page_title="Cartelera CDMX · Cinemex frente a Cinépolis", layout="wide")

# Marca Cinemex (DESIGN.md). Colores, radios y familias tipográficas vienen de .streamlit/config.toml;
# aquí solo lo que el tema no cubre: carga de fuentes, tarjetas con borde superior rojo, pesos y botones.
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800;900&family=Inter:wght@400;500;600;700&display=swap');
h1 {{ font-weight: 900 !important; letter-spacing: -0.01em; }}
h2 {{ font-weight: 800 !important; padding-top: 1.25rem; }}
h3 {{ font-weight: 700 !important; }}
[class*="st-key-card-"] {{
    border-top: 4px solid {RED} !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    background: {WHITE};
}}
[data-testid="stMetricValue"] {{ font-family: Montserrat, sans-serif; font-weight: 800; color: {GRAY_DARK}; }}
[data-testid="stMetricLabel"] {{ font-weight: 600; }}
.stButton > button {{ font-weight: 600; }}
.stButton > button[kind="primary"]:hover {{ background: {RED_DARK}; border-color: {RED_DARK}; }}
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
    if "sampled_at" in df.columns:
        df["sampled_at"] = df["sampled_at"].map(
            lambda s: datetime.fromisoformat(s).astimezone(TZ).strftime("%d/%m %I:%M %p").lstrip("0") if isinstance(s, str) else s)
    if "datetime_local" in df.columns:
        df["datetime_local"] = df["datetime_local"].map(
            lambda s: f"{date_es(s[:10])}, {time_12(s[11:16])}" if isinstance(s, str) and len(s) >= 16 else s)
    if "detected_at" in df.columns:
        df["detected_at"] = df["detected_at"].map(
            lambda s: datetime.fromisoformat(s).astimezone(TZ).strftime("%d/%m %I:%M %p").lstrip("0"))
    df = df.rename(columns=COLUMN_LABEL)
    if index:
        df = df.set_index(COLUMN_LABEL.get(index, index))
    return df


def has(v):
    """Valor numérico presente y mayor que cero (los LEFT JOIN dejan NaN)."""
    return v is not None and pd.notna(v) and float(v) > 0


def say(heads, *topics):
    """Frases de la lectura ejecutiva para los temas indicados."""
    for t in heads[heads.topic.isin(topics)].text:
        st.markdown(f"- {t}")


def card(title, host=st):
    """Contenedor con borde; la key `card-…` recibe el borde superior rojo de la marca (CSS de arriba)."""
    slug = "".join(ch if ch.isalnum() else "-" for ch in title.lower())
    return host.container(border=True, key=f"card-{slug}")


def pending(title, why, eta=None, kind="integration"):
    """Panel marcado como pendiente. Nunca muestra cifras."""
    badge = "Requiere integración con datos del cliente" if kind == "integration" else \
            "Requiere captura adicional" if kind == "capture" else f"Disponible a partir del {eta}"
    with card(title):
        st.markdown(f"**{title}**  \n:grey-background[{badge}]")
        st.caption(why)


def kpi_card(col, title, us, them, unit, delta_kind, note):
    """Tarjeta con ambas cadenas y el delta en la unidad correcta (pp para porcentajes)."""
    if delta_kind == "pp":
        delta = f"{us - them:+.1f} pp"
    elif delta_kind == "pct":
        delta = f"{100.0 * (us - them) / them:+.1f} %" if them else "—"
    else:
        delta = f"{us - them:+.0f}"
    fmt = (lambda v: f"{v:,.1f}{unit}") if isinstance(us, float) else (lambda v: f"{v:,}{unit}")
    with card(title, col):
        st.markdown(f"**{title}**")
        a, b = st.columns(2)
        a.metric("Cinemex", fmt(us), delta, help="Delta = Cinemex menos Cinépolis")
        b.metric("Cinépolis", fmt(them))
        st.caption(note)


# --- barra lateral: periodo y alcance -------------------------------------------------------------------
today_s = analytics.today()
today_d = date.fromisoformat(today_s)
cov = load("coverage")
if cov.empty:
    st.error("Todavía no hay datos capturados.")
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
st.sidebar.caption("Zonas de choque y mercados cautivos se habilitan al emparejar los cines de ambas "
                   "cadenas por distancia (siguiente fase).")

st.sidebar.header("Cómo leer las cifras")
st.sidebar.markdown(
    "**Todo se compara en porcentaje de la programación de cada cadena**, no en totales: Cinemex tiene "
    "más cines que Cinépolis en la plaza. Las diferencias entre porcentajes van en **puntos porcentuales (pp)**.\n\n"
    "**Dos unidades de oferta.** *Funciones* es cuántas proyecciones programa cada cadena. *Butacas ofertadas* "
    "es cuántos boletos podría vender: cada función vuelve a poner en venta todas las butacas de su sala, así que "
    "se suma el aforo de la sala por cada función de cada cine en los días del periodo. Es la medida correcta, "
    "porque una cadena puede dar más funciones y aun así ofrecer menos butacas si sus salas son más chicas.\n\n"
    + ("Para el día de hoy solo se cuentan funciones que aún no han empezado, en ambas cadenas.\n\n" if includes_today else "")
    + f"Los datos se capturan cada 15 minutos; esta página se refresca cada {TTL} segundos.")
with st.sidebar.expander("Glosario"):
    st.markdown(
        "- **Función.** Una proyección de una película en una sala a una hora.\n"
        "- **Aforo.** Butacas vendibles de una sala; se mide una vez por sala en el plano de asientos.\n"
        "- **Butacas ofertadas.** Suma del aforo de la sala por cada función del periodo: el máximo de boletos "
        "que la cadena podría vender en esos días. Ejemplo: un cine con 10 salas de 150 butacas y 5 funciones "
        "por sala oferta 7,500 butacas al día.\n"
        "- **Butacas ocupadas.** Boletos vendidos. En Cinépolis se leen del plano a una hora de la función; en "
        "Cinemex se estiman a partir de su semáforo de disponibilidad, calibrado con planos reales.\n"
        "- **Ocupación.** Butacas ocupadas entre butacas ofertadas.\n"
        "- **Share.** Parte de la programación de una cadena que se lleva una película, franja o formato, en % de "
        "sus propias funciones o butacas.\n"
        "- **Puntos porcentuales (pp).** Diferencia entre dos porcentajes. De 18 % a 21 % son +3 pp.\n"
        "- **Semana de cine.** De jueves a miércoles; es lo que ambas cadenas publican completo.\n"
        "- **Horario prime.** Viernes a domingo de 6:00 P.M. en adelante.")

# --- encabezado ---------------------------------------------------------------------------------------
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
heads = load("headlines", d0=d0, d1=d1)

st.title("Cartelera CDMX: Cinemex frente a Cinépolis")
st.markdown(f"**Periodo: {range_es(d0, d1)}.** Ciudad de México y área metropolitana.")
if kp.empty or len(kp) < 2:
    st.info("No hay cartelera publicada de ambas cadenas para ese periodo.")
    st.stop()
K = kp.set_index("chain")
us, them = K.loc["cinemex"], K.loc["cinepolis"]
updated = " · ".join(
    f"{CHAIN_LABEL.get(c, c)} {datetime.fromisoformat(r.taken_at).astimezone(TZ).strftime('%d/%m %I:%M %p').lstrip('0')}"
    for c, r in last_ok.iterrows())
st.caption(f"Alcance: {int(us.cinemas)} cines Cinemex y {int(them.cinemas)} Cinépolis · "
           f"{int(us.shows + them.shows):,} funciones publicadas en el periodo · "
           f"última captura {updated} (hora de la Ciudad de México). Datos reales de la cartelera pública de ambas cadenas.")
for name, age_min, err in stale:
    if age_min is None:
        st.warning(f"No hay ninguna captura buena de {name}.")
    elif err:
        st.warning(f"La última captura de {name} falló y el dato vigente tiene {age_min:.0f} minutos. "
                   f"Detalle técnico: {err[:120]}")
    else:
        st.warning(f"El dato de {name} tiene {age_min:.0f} minutos sin actualizarse; el scraper puede estar detenido.")

# --- 0. KPI strip ---------------------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
kpi_card(c1, "Funciones por cine y día", float(us.shows_per_cinema), float(them.shows_per_cinema), "", "pct",
         "Intensidad de programación. Se compara en % relativo porque es una cantidad, no un porcentaje.")
if us.weekend_shows and them.weekend_shows:
    kpi_card(c2, "Share de horario prime", float(us.pct_prime), float(them.pct_prime), " %", "pp",
             f"Parte de la parrilla de cada cadena en {PRIME_LABEL}: el bloque donde vive la taquilla.")
else:
    kpi_card(c2, "Share de tarde-noche", float(us.pct_evening), float(them.pct_evening), " %", "pp",
             "Parte de la parrilla de 6:00 P.M. en adelante. El periodo no incluye fin de semana, así que no hay horario prime.")
kpi_card(c3, "Share de funciones subtituladas", float(us.pct_subtitled), float(them.pct_subtitled), " %", "pp",
         "El resto es en español, doblada u original.")
kpi_card(c4, "Títulos distintos en cartelera", int(us.movies), int(them.movies), "", "abs",
         "Amplitud de la oferta. Los títulos se emparejan por nombre; los reestrenos pueden contarse dos veces.")
offered = load("offered_seats", d0=d0, d1=d1).set_index("chain") if True else None
p1, p2 = st.columns(2)
with p1:
    cp = offered.loc["cinepolis"] if "cinepolis" in offered.index else None
    cm = offered.loc["cinemex"] if "cinemex" in offered.index else None
    if cp is not None and has(cp.seats_offered):
        with card("butacas ofertadas"):
            st.markdown(f"**Butacas ofertadas {'hoy' if d0 == d1 == today_s else 'en el periodo'}: "
                        f"{int(max(cp.days, cm.days if cm is not None and has(cm.days) else 0))} día(s), "
                        f"{int(us.cinemas)} + {int(them.cinemas)} cines**")
            a, b = st.columns(2)
            if cm is not None and has(cm.seats_offered):
                a.metric("Cinemex", f"{int(cm.seats_offered):,}", f"{int(cm.avg_seats_per_show)} butacas por función", delta_color="off")
            else:
                a.metric("Cinemex", "pendiente", help="Falta la pasada de aforo por sala de Cinemex")
            b.metric("Cinépolis", f"{int(cp.seats_offered):,}", f"{int(cp.avg_seats_per_show)} butacas por función",
                     delta_color="off")
            known = " · ".join(f"{CHAIN_LABEL[c]} {r.pct_known:.0f} %" for c, r in offered.iterrows() if has(r.seats_offered))
            cap_all = load("capacity_summary").set_index("chain")
            physical = " y ".join(f"{CHAIN_LABEL[c]} tiene {int(r.seats):,} en {int(r.screens)} salas"
                                  for c, r in cap_all.iterrows()) or "aforo físico pendiente"
            st.caption("Máximo de boletos que cada cadena podría vender en los días del periodo: cada función vuelve a poner "
                       "en venta todas las butacas de su sala, así que se suma el aforo de la sala por cada función de cada "
                       f"cine de CDMX. No son butacas físicas ({physical}). Funciones con aforo conocido: {known}. "
                       "La ocupación, es decir cuántas de estas butacas se venden, se muestrea en Cinépolis y se estima por "
                       "semáforo calibrado en Cinemex (ver más abajo).")
    else:
        pending("Butacas ofertadas, ocupación estimada y butacas ocupadas por sala",
                "Cinépolis: la API pública entrega el plano de asientos de cada función en solo lectura. Cinemex: aforo y "
                "boletos vendidos llegan de sus propios datos por integración.", kind="capture")
with p2:
    pending("Tendencia de 4 semanas de cada indicador",
            "Las líneas de tendencia responden a “¿vamos mejorando?”. Necesitan cuatro semanas de historia; la "
            f"captura empezó el {date_es(FIRST_SNAPSHOT.isoformat())}.",
            eta=date_es((FIRST_SNAPSHOT + timedelta(weeks=4)).isoformat()), kind="history")

# --- 1. Decisiones -------------------------------------------------------------------------------------
st.header("¿Qué deberíamos abrir, mantener o recortar esta semana?")
pending("Decisiones de la semana: abrir sala, mantener o recortar por título",
        "La recomendación compara el share de pantalla de cada título con el share de butacas que realmente vende "
        "(regla: 2 pp o más por debajo de su demanda y al menos 5 % de las butacas, abrir; 2 pp o más por encima, "
        "recortar). El share de pantalla ya lo tenemos; el de butacas vendidas viene de los datos de taquilla del "
        "cliente o del muestreo de asientos. Mientras tanto, el panel siguiente muestra dónde apostamos distinto "
        "que Cinépolis.")

# --- 2. Asignación -------------------------------------------------------------------------------------
st.header("¿A qué películas les damos más pantalla que Cinépolis?")
say(heads, "peliculas", "exclusivas")
battle = load("movies_by_chain", d0=d0, d1=d1, limit=60)
battle["title"] = battle["title"].str.strip()
top = battle.head(15).copy()
order = top["title"].tolist()
long = top.melt(id_vars=["title"], value_vars=["share_cinemex", "share_cinepolis"], var_name="chain", value_name="share")
long["chain"] = long["chain"].str.replace("share_", "", regex=False)
ti = top.set_index("title")
long["shows"] = [ti.loc[t, f"shows_{c}"] for t, c in zip(long["title"], long["chain"])]
long["cinemas"] = [ti.loc[t, f"cinemas_{c}"] for t, c in zip(long["title"], long["chain"])]
long = long[long["shows"] > 0]
long["Cadena"] = long["chain"].map(CHAIN_LABEL)
top["delta"] = top.apply(lambda r: "solo Cinépolis" if r.shows_cinemex == 0 else
                         "solo Cinemex" if r.shows_cinepolis == 0 else f"{r.gap_pp:+.1f}", axis=1)
top["lado_label"] = top["gap_pp"].map(lambda v: CHAIN_LABEL["cinemex"] if v >= 0 else CHAIN_LABEL["cinepolis"])
y_axis = alt.Y("title:N", sort=order, title=None, axis=alt.Axis(labelLimit=280, grid=True, gridOpacity=0.35))
color = alt.Color("Cadena:N", scale=alt.Scale(domain=CHAIN_DOMAIN, range=CHAIN_RANGE),
                  legend=alt.Legend(orient="top", title=None))
rule = alt.Chart(long).mark_rule(strokeWidth=2, color=NEUTRAL).encode(
    y=y_axis, x=alt.X("min(share):Q", title="% de las funciones del periodo"), x2="max(share):Q")
dots = alt.Chart(long).mark_circle(size=110, opacity=1).encode(
    y=y_axis, x="share:Q", color=color,
    tooltip=[alt.Tooltip("title:N", title="Película"), alt.Tooltip("Cadena:N"),
             alt.Tooltip("share:Q", title="% de su programación", format=".1f"),
             alt.Tooltip("shows:Q", title="Funciones"), alt.Tooltip("cinemas:Q", title="Cines")])
delta = alt.Chart(top).mark_text(align="left", fontSize=13, fontWeight="bold").encode(
    y=alt.Y("title:N", sort=order, axis=None), x=alt.value(4), text="delta:N",
    color=alt.Color("lado_label:N", scale=alt.Scale(domain=CHAIN_DOMAIN, range=CHAIN_RANGE), legend=None),
    tooltip=[alt.Tooltip("title:N", title="Película"),
             alt.Tooltip("share_cinemex:Q", title="% programación Cinemex", format=".1f"),
             alt.Tooltip("share_cinepolis:Q", title="% programación Cinépolis", format=".1f"),
             alt.Tooltip("gap_pp:Q", title="Δ pp (Cinemex − Cinépolis)", format="+.1f")]
).properties(width=110, height=alt.Step(26), title=alt.TitleParams("Δ pp", fontSize=12, anchor="start"))
st.altair_chart(alt.hconcat((rule + dots).properties(width=560, height=alt.Step(26)), delta, spacing=6)
                .resolve_scale(y="shared").configure_view(strokeWidth=0), width="stretch")
st.caption("**Cómo leerla.** Cada fila es una película; los puntos son el porcentaje de la programación que le dedica "
           "cada cadena y la línea entre ellos la diferencia, que la columna Δ pp hace explícita (rojo: Cinemex "
           "apuesta más; gris: Cinépolis). Un solo punto es una exclusiva. Las 15 películas con más funciones.")
with st.expander("Ver todas las películas"):
    cols = ["title", "shows_cinemex", "shows_cinepolis", "cinemas_cinemex", "cinemas_cinepolis",
            "share_cinemex", "share_cinepolis", "gap_pp"]
    st.dataframe(pretty(battle[cols]), width="stretch", hide_index=True)
pending("Share de pantalla frente a share de butacas ocupadas por título",
        "El gráfico de asignación (un punto por película, diagonal de equilibrio, cuadrantes “sub-programado” y "
        "“sobre-programado”) necesita las butacas ocupadas de cada título. Es el mismo dato que habilita el panel de decisiones.")

# --- 2b. Butacas y ocupación (Cinépolis) --------------------------------------------------------------
st.header("¿Cuántas butacas pone Cinépolis en juego y qué tan llenas van?")
cap = load("capacity_summary")
if not cap.empty and "cinepolis" in set(cap.chain):
    C = cap.set_index("chain").loc["cinepolis"]
    st.markdown(f"- Cinépolis opera **{int(C.screens)} salas en {int(C.cinemas)} complejos** de la plaza con "
                f"**{int(C.seats):,} butacas**; la sala típica tiene {int(C.avg_seats)} asientos (de {int(C.min_seats)} a "
                f"{int(C.max_seats)}). {int(C.small)} salas tienen menos de 80 butacas, típicamente VIP.")
    bt = load("offered_by_title", d0=d0, d1=d1, limit=15)
    if not bt.empty:
        bt["title"] = bt["title"].str.strip()
        lead = bt.iloc[0]
        bigger = bt[bt.share_seats - bt.share_shows >= 1.5].head(3)
        smaller = bt[bt.share_shows - bt.share_seats >= 1.5].head(3)
        txt = (f"- {lead.title} se lleva el {lead.share_shows:.0f} % de las funciones de Cinépolis pero el "
               f"{lead.share_seats:.0f} % de sus butacas: la programa en salas grandes ({int(lead.avg_seats)} asientos en promedio).")
        if len(bigger):
            txt += " Salas grandes también para " + ", ".join(bigger.title.iloc[1:] if bigger.title.iloc[0] == lead.title else bigger.title) + "."
        if len(smaller):
            txt += " En salas chicas: " + ", ".join(smaller.title) + "."
        st.markdown(txt)
        c1, c2 = st.columns([3, 2])
        with c1:
            st.subheader("Funciones frente a butacas por película (Cinépolis)")
            longb = bt.melt(id_vars=["title", "shows", "seats", "avg_seats"], value_vars=["share_shows", "share_seats"],
                            var_name="medida", value_name="share")
            longb["Medida"] = longb["medida"].map({"share_shows": "% de funciones", "share_seats": "% de butacas"})
            orderb = bt["title"].tolist()
            yb = alt.Y("title:N", sort=orderb, title=None, axis=alt.Axis(labelLimit=280, grid=True, gridOpacity=0.35))
            ruleb = alt.Chart(longb).mark_rule(strokeWidth=2, color=NEUTRAL).encode(
                y=yb, x=alt.X("min(share):Q", title="% del total de Cinépolis en el periodo"), x2="max(share):Q")
            dotsb = alt.Chart(longb).mark_point(size=110, filled=True, opacity=1).encode(
                y=yb, x="share:Q",
                shape=alt.Shape("Medida:N", scale=alt.Scale(domain=["% de funciones", "% de butacas"], range=["circle", "square"]),
                                legend=alt.Legend(orient="top", title=None)),
                color=alt.Color("Medida:N", scale=alt.Scale(domain=["% de funciones", "% de butacas"],
                                                            range=[NEUTRAL, CHAIN_COLOR["cinepolis"]]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=[alt.Tooltip("title:N", title="Película"), alt.Tooltip("Medida:N"),
                         alt.Tooltip("share:Q", title="%", format=".1f"), alt.Tooltip("shows:Q", title="Funciones"),
                         alt.Tooltip("seats:Q", title="Butacas", format=","), alt.Tooltip("avg_seats:Q", title="Butacas por sala")])
            st.altair_chart((ruleb + dotsb).properties(height=alt.Step(26)).configure_view(strokeWidth=0), width="stretch")
            st.caption("**Cómo leerla.** El círculo claro es la parte de las funciones de Cinépolis que ocupa la película; el "
                       "cuadro gris oscuro, la parte de sus butacas. Cuando el cuadro queda a la derecha, la película va en salas "
                       "más grandes que el promedio: ahí está la apuesta real. Cinemex se añade al integrar su aforo por sala.")
        with c2:
            st.subheader("Salas y butacas por complejo")
            bc = load("capacity_by_cinema")
            st.dataframe(pretty(bc[["cinema_name", "screens", "seats", "avg_seats", "min_seats", "max_seats"]]),
                         width="stretch", hide_index=True, height=420)
    occ = load("occupancy_summary")
    n_samples = int(occ.samples.sum()) if not occ.empty else 0
    st.subheader("Ocupación muestreada a 60 minutos de la función (Cinépolis)")
    if n_samples == 0:
        st.info("Aún no hay muestras. El muestreo corre cada 15 minutos sobre las funciones que empiezan en una hora.")
    else:
        weighted = 100.0 * occ.sold.sum() / occ.seats.sum() if occ.seats.sum() else 0
        st.markdown(f"- {n_samples} funciones muestreadas hasta ahora; {weighted:.1f} % de las butacas vendidas a una hora de "
                    "empezar. La tabla cruza el color del semáforo del sitio de Cinépolis con el porcentaje real vendido, "
                    "para calibrar qué significa cada color.")
        st.dataframe(pretty(occ[["availability", "samples", "avg_sold_pct", "min_sold_pct", "max_sold_pct"]]),
                     width="stretch", hide_index=True)
        with st.expander("Últimas muestras"):
            st.dataframe(pretty(load("occupancy_recent", limit=50)), width="stretch", hide_index=True)
    cal = load("semaphore_calibration", chain="cinemex")
    st.subheader("Semáforo de Cinemex convertido a ocupación")
    if cal.empty:
        st.info("Cinemex publica alta, media o baja disponibilidad por función. Al calibrar cada nivel contra planos reales "
                "(una pasada única) el semáforo se convierte en % vendido estimado para todas sus funciones.")
    else:
        est = load("estimated_occupancy", d0=d0, d1=d1, chain="cinemex")
        if not est.empty and has(est.iloc[0].seats_occupied_est):
            e = est.iloc[0]
            st.markdown(f"- Cinemex: **{int(e.seats_occupied_est):,} butacas ocupadas estimadas** de {int(e.seats_offered):,} "
                        f"ofertadas en el periodo ({e.occupancy_pct_est:.1f} %), a partir del nivel de disponibilidad de "
                        f"cada función y su calibración ({int(e.shows_estimated):,} de {int(e.shows):,} funciones estimables).")
        st.dataframe(pretty(cal.rename(columns={"level": "availability"})[["availability", "samples", "sold_pct", "min_sold_pct", "max_sold_pct"]]),
                     width="stretch", hide_index=True)
    st.caption("Las muestras se acumulan con cada ronda; con una semana de datos se podrá reportar ocupación por película, "
               "franja y complejo. El dato exacto de Cinemex llegará de su taquilla por integración.")
else:
    pending("Butacas por sala y ocupación de Cinépolis",
            "Falta correr la pasada de aforo (`python3 -m scraper.sample --capacity`).", kind="capture")

# --- 3. Calidad del slot -------------------------------------------------------------------------------
st.header("¿Estamos en el horario donde vive la taquilla?")
say(heads, "prime", "franjas")
hm = load("heatmap_day_slot", d0=d0, d1=d1)
if not hm.empty:
    hm["gap_pp"] = (hm["share_cinemex"].fillna(0) - hm["share_cinepolis"].fillna(0)).round(1)
    hm["Día"] = hm["weekday"].map(lambda i: WEEKDAY_LABEL[int(i)])
    hm["Franja"] = hm["slot"].map(SLOT_SHORT)
    hm["label"] = hm["gap_pp"].map(lambda v: f"{v:+.1f}")
    lim = max(1.0, float(hm["gap_pp"].abs().max()))
    days_present = [d for d in WEEKDAY_LABEL if d in set(hm["Día"])]
    base = alt.Chart(hm).encode(
        x=alt.X("Franja:N", sort=[SLOT_SHORT[k] for k, *_ in SLOTS], title=None, axis=alt.Axis(labelAngle=0, orient="top", labelFontSize=12)),
        y=alt.Y("Día:N", sort=days_present, title=None))
    cells = base.mark_rect(stroke=WHITE, strokeWidth=2, cornerRadius=3).encode(
        color=alt.Color("gap_pp:Q", scale=alt.Scale(domain=[-lim, -lim / 2, 0, lim / 2, lim], range=DIVERGING,
                                                    interpolate="lab"),
                        legend=alt.Legend(title="Δ pp de parrilla", orient="right", gradientLength=160)),
        tooltip=[alt.Tooltip("Día:N"), alt.Tooltip("Franja:N"),
                 alt.Tooltip("share_cinemex:Q", title="% parrilla Cinemex", format=".1f"),
                 alt.Tooltip("share_cinepolis:Q", title="% parrilla Cinépolis", format=".1f"),
                 alt.Tooltip("gap_pp:Q", title="Δ pp", format="+.1f"),
                 alt.Tooltip("shows_cinemex:Q", title="Funciones Cinemex"), alt.Tooltip("shows_cinepolis:Q", title="Funciones Cinépolis")])
    text = base.mark_text(fontSize=12, fontWeight="bold").encode(
        text="label:N", color=alt.condition(f"abs(datum.gap_pp) > {lim * 0.55}", alt.value(WHITE), alt.value(GRAY_DARK)))
    st.altair_chart((cells + text).properties(height=alt.Step(44), width=alt.Step(150)).configure_view(strokeWidth=0), width="content")
    st.caption("**Cómo leerla.** Cada celda es un día y una franja. El número es la diferencia, en puntos porcentuales, "
               "entre la parte de la parrilla que Cinemex pone ahí y la que pone Cinépolis: rojo, ponemos más; gris, "
               "pone más Cinépolis. Solo aparecen los días del periodo elegido; la semana se completa cuando ambas "
               "cadenas la publican (miércoles o jueves). La ocupación real de cada franja se añadirá con el muestreo de asientos.")

# --- 4. Preventa -----------------------------------------------------------------------------------------
st.header("¿Qué estrenos vienen más fuertes de lo normal?")
pending("Curva de preventa frente a títulos comparables",
        "Boletos acumulados por día desde 14 días antes del estreno, contra la banda histórica de títulos del mismo "
        "perfil (tentpole, familiar, terror, drama). Un blockbuster concentra preventa anticipada y una comedia familiar "
        "vende la mayor parte el mismo día: comparar contra la curva equivocada lleva a cerrar salas que se llenarían "
        "de paso. Requiere la preventa del cliente por integración batch.")

# --- 5. Decaimiento --------------------------------------------------------------------------------------
st.header("¿Quién recorta más rápido después del estreno?")
pending("Decaimiento por título: funciones por semana con base 100 en la semana de estreno, ambas cadenas",
        "Muestra si cada cadena recorta agresivamente (segunda semana por debajo del 65 % de la primera) o conserva "
        "(por encima del 85 %). Ninguna de las dos es correcta por sí sola: depende de la ventana de estrenos. "
        "Necesita al menos dos semanas de cine completas en la historia.",
        eta=date_es((FIRST_SNAPSHOT + timedelta(weeks=2) + timedelta(days=(3 - FIRST_SNAPSHOT.weekday()) % 7)).isoformat()),
        kind="history")

# --- 6. Mix ----------------------------------------------------------------------------------------------
st.header("¿Con qué formatos e idiomas competimos?")
say(heads, "formato", "idioma")
mx = load("mix", d0=d0, d1=d1)
if not mx.empty:
    mx["Cadena"] = mx["chain"].map(CHAIN_LABEL)
    m1, m2 = st.columns([3, 2])
    for col, dim, buckets, label_map, title in ((m1, "format", FORMAT_BUCKETS, FORMAT_LABEL, "Formato de sala"),
                                                (m2, "language", LANGUAGE_BUCKETS, LANGUAGE_LABEL, "Idioma")):
        sub = mx[mx.dimension == dim].copy()
        sub["Grupo"] = sub["bucket"].map(label_map)
        sub["orden"] = sub["bucket"].map({b: i for i, b in enumerate(buckets)})
        sub["label"] = sub["share"].map(lambda v: f"{v:.0f} %" if v >= 6 else "")
        domain = [label_map[b] for b in buckets]
        bars = alt.Chart(sub).mark_bar(cornerRadius=2, stroke=WHITE, strokeWidth=2).encode(
            y=alt.Y("Cadena:N", sort=CHAIN_DOMAIN, title=None),
            x=alt.X("share:Q", stack="normalize", title="% de las funciones", axis=alt.Axis(format="%")),
            order=alt.Order("orden:Q"),
            color=alt.Color("Grupo:N", scale=alt.Scale(domain=domain, range=RED_RAMP[:len(domain)]),
                            legend=alt.Legend(orient="top", title=None, columns=4)),
            tooltip=[alt.Tooltip("Cadena:N"), alt.Tooltip("Grupo:N"), alt.Tooltip("share:Q", title="% de su programación", format=".1f"),
                     alt.Tooltip("shows:Q", title="Funciones")])
        labels = alt.Chart(sub).mark_text(fontSize=12, fontWeight="bold").encode(
            y=alt.Y("Cadena:N", sort=CHAIN_DOMAIN), x=alt.X("share:Q", stack="normalize", bandPosition=0.5),
            order=alt.Order("orden:Q"), text="label:N", detail="Grupo:N",
            color=alt.condition("datum.orden >= 2", alt.value(GRAY_DARK), alt.value(WHITE)))  # texto oscuro sobre rosas claros
        col.subheader(title)
        col.altair_chart((bars + labels).properties(height=150), width="stretch")
    st.caption("**Cómo leerla.** Cada barra es el 100 % de las funciones de una cadena en el periodo. Premium / VIP agrupa "
               "salas Premium, Platino, VIP y Confort; Gran formato agrupa IMAX, XE, ScreenX, Dolby Atmos y Jumbo; "
               "“Español” incluye doblada y en español original.")
pr = load("prices")
if not pr.empty:
    st.subheader("Precio del boleto general por formato y tipo de día")
    piv = pretty(pr).pivot_table(index=["Formato", "Tipo de día"], columns="Cadena", values="Precio general (mediana)", aggfunc="first")
    piv = piv.reindex([(FORMAT_LABEL[b], DAY_TYPE_LABEL[d]) for b in FORMAT_BUCKETS for d in ("weekday", "promo", "weekend")
                       if (FORMAT_LABEL[b], DAY_TYPE_LABEL[d]) in piv.index])
    st.dataframe(piv.style.format("${:,.0f}", na_rep="—"), width="stretch")
    n_cin = pr.groupby("chain").cinemas.max()
    st.caption("**Cómo leerla.** Mediana del boleto de adulto regular entre los cines muestreados "
               + ", ".join(f"{CHAIN_LABEL[c]}: {int(n)} cines" for c, n in n_cin.items())
               + ". Una función por cine, formato y tipo de día, renovada cada semana. Martes y miércoles son los días de "
               "precio reducido en ambas cadenas. Precios en pesos, sin cargo por servicio.")
    with st.expander("Detalle por cadena, formato y tipo de día"):
        st.dataframe(pretty(pr[["chain", "format_bucket", "day_type", "samples", "median_price", "min_price", "max_price"]]),
                     width="stretch", hide_index=True)
pending("Ingreso potencial por butaca ofertada",
        "Σ(mix de formato × precio) por butaca: cierra el argumento de monetización. Requiere el aforo por sala de Cinemex.",
        kind="integration")

# --- 7. Geografía ------------------------------------------------------------------------------------
st.header("¿Dónde está el hueco geográfico más caro?")
pending("Oferta por cada 100 mil habitantes por alcaldía, con zonas de choque y mercados cautivos",
        "Tenemos la ubicación de todos los cines de ambas cadenas. Falta asignar cada cine a su alcaldía, cargar la "
        "población del INEGI y marcar las zonas de choque a partir del emparejamiento de cines por distancia.",
        kind="capture")

# --- 8. Concentración ---------------------------------------------------------------------------------
st.header("¿Apostamos fuerte o cubrimos ancho?")
say(heads, "concentracion")
cc = load("concentration", d0=d0, d1=d1)
if len(cc) == 2:
    C = cc.set_index("chain")
    g1, g2, g3 = st.columns(3)
    kpi_card(g1, "Índice de concentración de la parrilla (HHI)", int(C.loc["cinemex"].hhi), int(C.loc["cinepolis"].hhi), "", "abs",
             "Suma de los cuadrados del share de cada título. 10,000 sería una sola película; por debajo de 1,500 la parrilla "
             "está repartida, por encima de 2,500 está concentrada.")
    kpi_card(g2, "Peso de las 3 películas más programadas", float(C.loc["cinemex"].top3_pct), float(C.loc["cinepolis"].top3_pct), " %", "pp",
             "Parte de la parrilla que se llevan los tres títulos principales.")
    kpi_card(g3, "Títulos distintos por complejo", float(C.loc["cinemex"].titles_per_cinema), float(C.loc["cinepolis"].titles_per_cinema), "", "pct",
             "Promedio de películas distintas que ofrece cada cine en el periodo.")
    st.caption("**Lo que dice.** Concentrar es coherente cuando la ventana de estrenos es fuerte y cara cuando no lo es. "
               "Se lee junto al calendario de estrenos, nunca sola.")

# --- 9. Operación: cambios --------------------------------------------------------------------------------
st.header("¿Qué cambió en la cartelera ya publicada?")
say(heads, "cambios")
with st.expander("¿Qué significa cada tipo de cambio?"):
    for k in KINDS:
        st.markdown(f"- **{KIND_LABEL[k]}.** {KIND_HELP[k]}")
by_kind = load("events_by_kind", since_hours=24)
if not by_kind.empty:
    st.dataframe(pretty(by_kind).pivot_table(index="Cadena", columns="Tipo de cambio", values="Cambios", fill_value=0, aggfunc="sum"),
                 width="stretch")
kinds = st.multiselect("Mostrar", KINDS, default=KINDS[:4], format_func=lambda k: KIND_LABEL[k])
events = load("recent_events", limit=300, kinds=kinds or None)
if events.empty:
    st.info("Sin cambios de ese tipo.")
else:
    st.dataframe(pretty(events.drop(columns=["show_id", "date"])), width="stretch", hide_index=True)
st.caption("Cuando una cadena publica la semana siguiente (miércoles o jueves) aparecen miles de funciones nuevas de golpe; "
           "eso es publicación, no cambios sobre lo ya anunciado.")

# --- pie -------------------------------------------------------------------------------------------------
st.divider()
st.caption("Fuentes: cartelera pública de Cinemex y Cinépolis, capturada cada 15 minutos para los cines de la Ciudad de "
           "México y área metropolitana. Previsto: aforo por sala y muestreo de disponibilidad de asientos a 60 minutos "
           "de cada función; integración batch de preventa y taquilla del cliente. Las películas se emparejan por título "
           "hasta contar con la tabla de equivalencias entre cadenas.")
