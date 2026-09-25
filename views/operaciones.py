"""Operaciones (solo admin): el estado de la plataforma para quien la opera. Captura de cartelera y muestreos
(lo mismo que `scraper.health`, en vivo), corridas recientes con su error literal, los trabajos programados con su
última corrida y memoria, el servidor (commit, respaldo, tamaño de `snapshots.db` y `app.db`) y la cola de cada log. Es la única página que muestra nombres internos (tablas, logs)
tal cual: su público es ingeniería, no el cliente. Toda lectura pasa por `load_health` y `load_ops`."""
from ui import session
from ui.common import *  # noqa: F401,F403

me = st.session_state["auth"]["user"]
session.require_admin(me)

HOURS = 24
RUN_DAYS = 7
LOG_LINES = 60


def estado(ok, label_ok=None, label_bad=None):
    """Chip de estado: verde apagado si está bien, ámbar si no. El rojo queda para Cinemex."""
    return (f'<span class="estado">{esc(label_ok or OPS_TEXT["ok"])}</span>' if ok
            else f'<span class="estado mal">{esc(label_bad or OPS_TEXT["failed"])}</span>')


def age_text(minutes):
    if minutes is None:
        return OPS_TEXT["never"]
    return OPS_TEXT["ago_h"].format(hours=n(minutes / 60, 1)) if minutes >= 120 else OPS_TEXT["ago"].format(minutes=n(minutes))


def when(v):
    return local_time(v) or "—"


def encabezado(slug, titulo, lead):
    md(f'<h3 class="pregunta">{esc(titulo)}</h3><p class="nota">{esc(lead)}</p>')


md(f"""
<div class="enc">
  <h1>{esc(OPS_TEXT["title"])}</h1>
  <div class="meta"><span>{esc(OPS_TEXT["lead"])}</span></div>
</div>
""")

# --- resumen: lo que diría scraper.health ahora mismo ----------------------------------------------------
if not config.DB_PATH.exists():
    st.warning(OPS_TEXT["no_snapshots"])
    report = None
else:
    report = load_health("check", hours=HOURS)
    if report["ok"]:
        st.success(OPS_TEXT["all_ok"].format(hours=HOURS))
    else:
        st.warning(OPS_TEXT["problems"].format(n=len(report["problems"]), hours=HOURS) + "\n\n"
                   + "\n".join(f"- {p}" for p in report["problems"]))
    md(f'<p class="nota">{esc(OPS_TEXT["checked_at"])}: {esc(when(report["at"]))} · {esc(OPS_TEXT["window"])}: '
       f'{esc(OPS_TEXT["hours"].format(n=HOURS))}</p>')

# --- captura por cadena ----------------------------------------------------------------------------------
if report:
    with seccion("captura"):
        encabezado("captura", OPS_TEXT["capture"], OPS_TEXT["capture_lead"])
        chains = [c for c in CHAINS if report["chains"].get(c)]
        rows = []

        def fila(label, fn, cls_fn=None):
            cells = [label]
            for c in chains:
                v = fn(report["chains"][c])
                cells.append((v, cls_fn(report["chains"][c])) if cls_fn else v)
            rows.append(cells)

        fila(OPS_TEXT["last_at"], lambda c: when(c["last_at"]))
        fila(OPS_TEXT["last_age"], lambda c: age_text(c["last_age_min"]), lambda c: "mal" if c["last_age_min"] > MAX_AGE_MIN else "")
        fila(OPS_TEXT["last_result"], lambda c: OPS_TEXT["ok"] if c["last_ok"] else OPS_TEXT["failed"], lambda c: "" if c["last_ok"] else "mal")
        fila(OPS_TEXT["last_shows"], lambda c: n(c["last_shows"]))
        fila(OPS_TEXT["last_cinemas"], lambda c: f"{n(c['last_cinemas'])} ({n(c['peak_cinemas_7d'])})" if c.get("peak_cinemas_7d") else n(c.get("last_cinemas")),
             lambda c: "mal" if c.get("peak_cinemas_7d") and (c.get("last_cinemas") or 0) < health.COVERAGE_MIN_RATIO * c["peak_cinemas_7d"] else "")
        fila(OPS_TEXT["captures"], lambda c: n(c["snapshots"]))
        fila(OPS_TEXT["expected"], lambda c: n(c["expected"]))
        fila(OPS_TEXT["missing"], lambda c: ", ".join(c["missing"]) if c["missing"] else OPS_TEXT["none"], lambda c: "mal" if c["missing"] else "")
        fila(OPS_TEXT["failed_runs"], lambda c: n(c["failed"]), lambda c: "mal" if c["failed"] else "")
        fila(OPS_TEXT["occ_t60"], lambda c: n(c["occupancy_t60"]))
        fila(OPS_TEXT["occ_post"], lambda c: n(c["occupancy_post_start"]))
        fila(OPS_TEXT["prices_7d"], lambda c: n(c["prices_7d"]))
        fila(OPS_TEXT["concessions_8d"], lambda c: n(c["concession_cinemas_8d"]))
        fila(OPS_TEXT["delivery_8d"], lambda c: n(c["delivery_stores_8d"]))
        fila(OPS_TEXT["calibration"], lambda c: ", ".join(f"{k}: {v}" for k, v in c["calibration"].items()) if "calibration" in c else "—")
        table([OPS_TEXT["signal"], *[CHAIN_LABEL[c] for c in chains]], rows)

# --- trabajos programados: el registro y lo que dejó jobs.run -------------------------------------------------
with seccion("trabajos"):
    encabezado("trabajos", OPS_TEXT["jobs"], OPS_TEXT["jobs_lead"])
    job_days = st.slider(OPS_TEXT["jobs_days"], min_value=1, max_value=30, value=RUN_DAYS, key="job_days")
    jobs = pd.DataFrame(load_ops("jobs_status", days=job_days))
    jobs["last_status"] = jobs["last_status"].map(OPS_TEXT["jobs_status"]).fillna("—")
    jobs["schedule"] = jobs["schedule"].where(jobs["enabled"], jobs["schedule"] + f' · {OPS_TEXT["jobs_off"]}')
    st.dataframe(pretty(jobs[["key", "area", "schedule", "last_started_at", "last_status", "last_duration_s", "last_max_rss_mb",
                              "runs", "failures", "peak_rss_mb", "timeout_min"]]),
                 width="stretch", hide_index=True,
                 column_config={COLUMN_LABEL[c]: st.column_config.NumberColumn(format="%.0f")
                                for c in ("last_duration_s", "last_max_rss_mb", "peak_rss_mb")})

# --- cobertura por geografía: el registro para decidir dónde muestrear planos ---------------------------------
if report:
    with seccion("cobertura"):
        encabezado("cobertura", OPS_TEXT["coverage"], OPS_TEXT["coverage_lead"])
        md(f'<p class="nota">{esc(OPS_TEXT["coverage_seats"].format(plazas=", ".join(PLAZA_LABEL.get(p, p) for p in config.SEATS_PLAZAS)))}</p>')
        cov = load("plaza_coverage")
        if not cov.empty:
            cov["plaza"] = cov["plaza"].fillna(OPS_TEXT["coverage_no_plaza"])
            st.dataframe(pretty(cov[["chain", "plaza", "city_id", "state_id", "sample_cinema", "cinemas", "shows"]]),
                         width="stretch", hide_index=True, height=min(500, 38 * (len(cov) + 1)))

# --- corridas recientes ----------------------------------------------------------------------------------
if report:
    with seccion("corridas"):
        encabezado("corridas", OPS_TEXT["runs"], OPS_TEXT["runs_lead"])
        days = st.slider(OPS_TEXT["runs_days"], min_value=1, max_value=30, value=RUN_DAYS, key="run_days")
        runs = pd.DataFrame(load_health("recent_runs", days=days))
        if runs.empty:
            st.info(OPS_TEXT["runs_empty"])
        else:
            runs["ok"] = runs["ok"].fillna(0).astype(int).astype(bool)
            plot = runs.assign(chain_label=runs["chain"].map(CHAIN_LABEL), at=pd.to_datetime(runs["taken_at"], utc=True).dt.tz_convert(TZ),
                               duration_s=runs["duration_s"].fillna(0))
            leyenda([(CHAIN_LABEL[c], CHAIN_COLOR[c]) for c in CHAINS] + [(OPS_TEXT["runs_failed_legend"], WARN)])
            base = alt.Chart(plot).encode(
                x=alt.X("at:T", title=OPS_TEXT["runs_chart_x"], axis=alt.Axis(format="%d/%m %H:%M")),
                y=alt.Y("duration_s:Q", title=OPS_TEXT["runs_chart_y"]),
                tooltip=[alt.Tooltip("chain_label:N", title=COLUMN_LABEL["chain"]), alt.Tooltip("at:T", title=COLUMN_LABEL["taken_at"], format="%d/%m %H:%M"),
                         alt.Tooltip("duration_s:Q", title=COLUMN_LABEL["duration_s"], format=".0f"),
                         alt.Tooltip("n_shows:Q", title=COLUMN_LABEL["n_shows"], format=","), alt.Tooltip("calls:Q", title=COLUMN_LABEL["calls"])])
            good = base.transform_filter(alt.datum.ok).mark_circle(size=70).encode(
                color=alt.Color("chain_label:N", scale=alt.Scale(domain=CHAIN_DOMAIN, range=CHAIN_RANGE), legend=None))
            bad = base.transform_filter(~alt.datum.ok).mark_point(size=110, shape="cross", filled=True, color=WARN)
            chart((good + bad).properties(height=200))
            shown = runs[["taken_at", "chain", "ok", "n_shows", "n_cinemas", "n_events", "calls", "duration_s", "error"]]
            st.dataframe(pretty(shown), width="stretch", hide_index=True,
                         column_config={COLUMN_LABEL["ok"]: st.column_config.CheckboxColumn(),
                                        COLUMN_LABEL["duration_s"]: st.column_config.NumberColumn(format="%.0f")})

# --- unidades de captura: qué estado o lote falló ------------------------------------------------------------
if report:
    with seccion("unidades"):
        encabezado("unidades", OPS_TEXT["units"], OPS_TEXT["units_lead"])
        unit_days = st.slider(OPS_TEXT["runs_days"], min_value=1, max_value=30, value=RUN_DAYS, key="unit_days")
        cap_units = pd.DataFrame(load_health("capture_units", days=unit_days))
        if cap_units.empty:
            st.info(OPS_TEXT["units_empty"])
        else:
            st.dataframe(pretty(cap_units[["chain", "label", "unit", "last_at", "last_ok", "last_error", "runs", "failures",
                                           "avg_shows", "avg_calls", "avg_duration_s"]]),
                         width="stretch", hide_index=True,
                         column_config={COLUMN_LABEL["last_ok"]: st.column_config.CheckboxColumn(),
                                        COLUMN_LABEL["avg_duration_s"]: st.column_config.NumberColumn(format="%.0f")})

# --- servidor y almacenamiento -----------------------------------------------------------------------------
with seccion("servidor"):
    encabezado("servidor", OPS_TEXT["server"], OPS_TEXT["server_lead"])
    dep, sto = load_ops("deployment"), load_ops("storage")
    commit = f'{dep["commit"]} · {when(dep["commit_at"])} · {dep["commit_subject"]}' if dep["commit"] else OPS_TEXT["no_git"]
    table(["", ""], [
        [OPS_TEXT["commit"], commit],
        [OPS_TEXT["last_deploy"], dep["last_deploy"] or OPS_TEXT["no_line"]],
        [OPS_TEXT["last_backup"], dep["last_backup"] or OPS_TEXT["no_line"]],
        [OPS_TEXT["db_file"], size_h(sto["db_bytes"])],
        [OPS_TEXT["wal_file"], size_h(sto["wal_bytes"])],
        [OPS_TEXT["app_db_file"], size_h(sto["app_db_bytes"])],
        [OPS_TEXT["raw_dir"], size_h(sto["raw_bytes"])],
        [OPS_TEXT["backups_dir"], size_h(sto["backups_bytes"])],
        [OPS_TEXT["disk_free"], f'{size_h(sto["disk_free_bytes"])} de {size_h(sto["disk_total_bytes"])} · {sto["data_dir"]}'],
    ])

# --- logs -------------------------------------------------------------------------------------------------
with seccion("logs"):
    encabezado("logs", OPS_TEXT["logs"], OPS_TEXT["logs_lead"])
    c1, c2 = st.columns([2, 1])
    name = c1.selectbox(OPS_TEXT["log"], options=list(health.LOGS), format_func=health.LOGS.get, key="log_name")
    lines = c2.select_slider(OPS_TEXT["lines"], options=[20, 60, 200, 500], value=LOG_LINES, key="log_lines")
    tail = load_ops("log_tail", name=name, lines=lines)
    if not tail["lines"]:
        st.info(OPS_TEXT["log_empty"])
    else:
        md(f'<p class="nota">{esc(OPS_TEXT["log_meta"].format(size=size_h(tail["size_bytes"]), when=when(tail["modified_at"])))}</p>')
        st.code("\n".join(tail["lines"]), language=None, line_numbers=False, wrap_lines=True)

# --- pendiente --------------------------------------------------------------------------------------------
md(f'<div class="desbloqueo"><h3>{esc(OPS_TEXT["pending"])}</h3><p>{esc(OPS_TEXT["pending_lead"])}</p><div class="desb-grid">'
   + "".join(f'<div class="desb-item"><div class="cuando">{esc(a)}</div><div class="que">{esc(b)}</div><p>{esc(c)}</p></div>'
             for a, b, c in OPS_TEXT["pending_items"])
   + "</div></div>")
