"""Página de dulcería: precio en sala de Cinépolis por complejo y comparación a domicilio (Rappi, DiDi Food).
No depende del periodo ni de la franja: los precios de dulcería no cambian con la función."""
from ui.common import *  # noqa: F401,F403

if not config.DB_PATH.exists():
    st.info("Aún no hay datos: la base no existe todavía. Ver la página de cartelera.")
    st.stop()

today_s = analytics.today()
this_w0, this_w1 = analytics.cinema_week(today_s)
concl = load_raw("conclusions", d0=this_w0, d1=this_w1, shown=SHOWN_MOVIES, total=TOTAL_MOVIES)
hallazgos = [f for f in load_raw("findings", d0=this_w0, d1=this_w1, top=6) if f["topic"] == "dulceria"]

md("""
<div class="enc">
  <h1>Dulcería: <span>Cinemex</span> frente a Cinépolis</h1>
  <div class="meta">
    <span><strong>Sala:</strong> menú en línea de Cinépolis por complejo</span>
    <span><strong>A domicilio:</strong> Rappi y DiDi Food, ambas cadenas</span>
    <span>Nuestro tablero de sala llega con tus datos</span>
  </div>
</div>
""")

capa(1, "Lo que importa hoy", "El hallazgo de dulcería, si cruza su umbral; el mismo que aparece en la cartelera.", roja=True)
if not hallazgos:
    st.info("La brecha de dulcería no cruza el umbral de relevancia.")
for f in hallazgos:
    hallazgo(f)

capa(2, "Evidencia", "Precio en sala por complejo (Cinépolis) y comparación a domicilio, plataforma contra plataforma.")
# --- Dulcería: precio en sala y a domicilio ------------------------------------------------------------
with seccion("dulceria"):
    pregunta("¿Cómo compite nuestra dulcería con la de Cinépolis?", concl.get("dulceria", ""),
             "En sala solo tenemos el menú de Cinépolis; nuestra lista llega con tus datos. La comparación directa es a domicilio, plataforma contra plataforma.")
    cs = load("concession_summary")
    dv = load("delivery_summary")
    if cs.empty and dv.empty:
        st.info("Aún no hay lecturas de dulcería.")
    else:
        leyenda([(CHAIN_LABEL["cinemex"], CHAIN_COLOR["cinemex"]), (CHAIN_LABEL["cinepolis"], CHAIN_COLOR["cinepolis"])])
        g1, g2 = st.columns([3, 2])
        with g1:
            st.markdown("**A domicilio: precio mediano por tipo de producto**")
            plat = st.radio("Plataforma", ["Ambas", "rappi", "didi"], format_func=lambda v: PLATFORM_LABEL.get(v, v), horizontal=True,
                            key="dlv_plat", label_visibility="collapsed")
            cmp_ = load("delivery_compare", platform=None if plat == "Ambas" else plat)
            cmp_ = cmp_[cmp_.cinemex_median.notna() | cmp_.cinepolis_median.notna()] if not cmp_.empty else cmp_
            if cmp_.empty:
                st.info("Sin lecturas de dulcería a domicilio.")
            else:
                longc = cmp_.melt(id_vars=["label", "delta_pct"], value_vars=["cinemex_median", "cinepolis_median"], var_name="chain", value_name="price")
                longc["chain"] = longc["chain"].str.replace("_median", "")
                longc["Cadena"] = longc["chain"].map(CHAIN_LABEL)
                longc = longc.dropna(subset=["price"])
                order = cmp_["label"].tolist()
                bars = alt.Chart(longc).mark_bar(height=11).encode(
                    y=alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelColor=GRAY_DARK, ticks=False, domain=False)),
                    yOffset=alt.YOffset("Cadena:N", sort=CHAIN_DOMAIN),
                    x=alt.X("price:Q", title="Pesos", axis=alt.Axis(format="$,.0f")),
                    color=alt.Color("Cadena:N", scale=alt.Scale(domain=CHAIN_DOMAIN, range=CHAIN_RANGE), legend=None),
                    tooltip=[alt.Tooltip("label:N", title="Producto"), alt.Tooltip("Cadena:N"), alt.Tooltip("price:Q", title="Mediana", format="$,.0f"),
                             alt.Tooltip("delta_pct:Q", title="Δ Cinépolis vs Cinemex %", format="+.0f")])
                chart(bars.properties(height=alt.Step(30)))
                rows_ = []
                for r in cmp_.itertuples():
                    a_, c_ = r.cinemex_median, r.cinepolis_median
                    delta = f"{r.delta_pct:+.0f} %".replace("-", "−") if pd.notna(r.delta_pct) else ""
                    rows_.append([r.label, (f"${a_:,.0f}" if has(a_) else "—", "cmx"), r.cinemex_product or "—",
                                  (f"${c_:,.0f}" if has(c_) else "—", "cnp"), r.cinepolis_product or "—", delta])
                table(["Producto comparable", "Cinemex", "Nuestro producto", "Cinépolis", "Su producto", "Δ Cinépolis vs Cinemex"], rows_, num_cols=(1, 3, 5))
        with g2:
            if not cs.empty and has(cs.iloc[0].cinemas):
                bk = load("concession_basket")
                B = {r.product_name: r for r in bk.itertuples()}
                st.markdown(f"**En sala: {CHAIN_LABEL['cinepolis']} fija el precio por complejo**")
                prod = st.selectbox("Producto", [x for x in analytics.BASKET if x in B], key="conc_prod", label_visibility="collapsed")
                pc = load("concession_product_by_cinema", product_name=prod)
                if not pc.empty:
                    pc["vip"] = pc["cinema_type"].map(CINEMA_TYPE_LABEL)
                    med = float(B[prod].median_price)
                    barsc = alt.Chart(pc).mark_bar().encode(
                        y=alt.Y("cinema_name:N", sort=None, title=None, axis=alt.Axis(labelLimit=170, labelColor=GRAY_DARK, ticks=False, domain=False, labelFontSize=10)),
                        x=alt.X("price:Q", title="Pesos", axis=alt.Axis(format="$,.0f")),
                        color=alt.Color("vip:N", scale=alt.Scale(domain=[CINEMA_TYPE_LABEL["traditional"], CINEMA_TYPE_LABEL["vip"]],
                                                                range=[CHAIN_COLOR["cinepolis"], NEUTRAL]), legend=alt.Legend(orient="top", title=None)),
                        tooltip=[alt.Tooltip("cinema_name:N", title="Complejo"), alt.Tooltip("price:Q", title="Precio", format="$,.0f"), alt.Tooltip("vip:N", title="Tipo")])
                    rule = alt.Chart(pd.DataFrame({"m": [med]})).mark_rule(color=GRAY, strokeDash=[4, 3]).encode(x="m:Q")
                    chart((barsc + rule).properties(height=alt.Step(9)))
                    md(f'<p class="nota">{esc(prod)}: de ${B[prod].min_price:,.0f} a ${B[prod].max_price:,.0f} en {int(B[prod].cinemas)} complejos, '
                       f'{int(B[prod].distinct_prices)} precios distintos; la línea punteada es la mediana (${med:,.0f}).</p>')
        with st.expander("Detalle: canasta de Cinépolis por complejo, catálogo a domicilio y tiendas"):
            if not cs.empty and has(cs.iloc[0].cinemas):
                bk = load("concession_basket")
                table(["Producto", "Complejos", "Mediana", "Mínimo", "Máximo", "Máx. vs mín.", "Precios distintos"],
                      [[r.product_name, n(r.cinemas), (f"${r.median_price:,.0f}", "cnp"), f"${r.min_price:,.0f}", f"${r.max_price:,.0f}",
                        f"+{r.spread_pct:.0f} %", n(r.distinct_prices)] for r in bk.itertuples()], num_cols=range(1, 7))
                bc = load("concession_by_cinema")
                cols = ["cinema_name", "products", "median_price"] + [x for x in analytics.BASKET if x in bc.columns]
                st.dataframe(pretty(bc[cols]), width="stretch", hide_index=True, height=300)
            if not dv.empty:
                table(["Plataforma", "Cadena", "Tiendas", "Productos", "% con precio único", "Última lectura"],
                      [[PLATFORM_LABEL.get(r.platform, r.platform), (CHAIN_LABEL[r.chain], "cmx" if r.chain == "cinemex" else "cnp"),
                        n(r.stores), n(r.products), (f"{r.pct_single_price:.0f} %" if pd.notna(r.pct_single_price) else "—"), local_time(r.last_sampled)]
                       for r in dv.itertuples()], num_cols=(2, 3, 4))
                ch = st.radio("Cadena", CHAINS, format_func=lambda c: CHAIN_LABEL[c], horizontal=True, key="dlv_chain")
                d1_, d2_ = st.columns([3, 2])
                dp = load("delivery_products", chain=ch, platform=None if plat == "Ambas" else plat)
                d1_.dataframe(pretty(dp[["product_name", "category", "stores", "median_price", "min_price", "max_price", "distinct_prices"]]),
                              width="stretch", hide_index=True, height=360)
                ds = load("delivery_stores", chain=ch, platform=None if plat == "Ambas" else plat)
                if not ds.empty:
                    ds["platform"] = ds["platform"].map(PLATFORM_LABEL)
                    d2_.dataframe(pretty(ds[["platform", "store_name", "products", "median_price"]]), width="stretch", hide_index=True, height=360)
    leerla("dulceria",
           "A domicilio se compara la mediana entre tiendas de cada cadena en la misma plataforma (Rappi, DiDi Food), agrupando "
           "productos por tipo porque cada cadena los nombra distinto; es el catálogo para llevar (Mega Palomitas de 230 g, refresco "
           "en lata), no el tablero de sala, y las porciones difieren: nuestro combo básico lleva dos latas y el de Cinépolis un refresco. "
           "En sala solo existe el menú en línea de Cinépolis, por complejo; palomitas y refresco van por tamaño y se muestra el "
           "tamaño base. Cinemex tiene apagada la venta de dulcería en línea, así que nuestro tablero de sala llega con tus datos. "
           "Uber Eats no se lee porque sus términos prohíben la extracción.")

st.page_link("views/cartelera.py", label="Volver a la cartelera", icon=":material/movie:")
md(f'<p class="pie">Fuentes: menú de dulcería en línea de Cinépolis por complejo; catálogo de dulcería a domicilio de ambas cadenas en '
   f'Rappi y DiDi Food, renovado cada semana. Cinemex tiene apagada la venta de dulcería en línea. Historia desde el '
   f'{esc(date_es(FIRST_SNAPSHOT.isoformat()))}.</p>')
