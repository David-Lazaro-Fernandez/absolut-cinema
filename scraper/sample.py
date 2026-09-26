"""Muestreo de asientos y precios (ver project.md > "Asientos y precios").

Uso:
  python3 -m scraper.sample --capacity [--chain cinemex]   # aforo por sala; una pasada, repetir al mes
  python3 -m scraper.sample --occupancy                    # Cinépolis: planos a 45–75 min de empezar (preventa; a mano)
  python3 -m scraper.sample --post-start [--chain cinemex] # planos 15–75 min después de empezar (cada hora, ambas
                                                           # cadenas); es la asistencia final y el target del modelo de consumo
  Los planos (--capacity, --occupancy, --post-start) solo miran las plazas de config.SEATS_PLAZAS (AC_SEATS_PLAZAS,
  por defecto cdmx); --plazas gdl,mty las cambia para esa corrida y --plazas all recorre todos los cines capturados
  (la pasada nacional única de aforo, a mano: decisión 2026-09-12). Precios y dulcería van sobre todos los cines.
  python3 -m scraper.sample --occupancy --chain cinemex --per-level 100 --lead 60 --tolerance 45
                                                           # Cinemex: calibración del semáforo, N por nivel, una vez
  python3 -m scraper.sample --prices [--limit N]           # boletos de una función por cine, formato y tipo de día
  python3 -m scraper.sample --concessions [--limit N]      # Cinépolis: menú de dulcería con precios por cine (cada 7 días)
                                                           # (weekday lun/jue, promo mar/mié, weekend vie–dom)
  opciones: --lead 60 --tolerance 15 --after 20 --refresh --dry-run --limit N

Cinépolis: `query Seats` y `query Tickets` en /v1/ticket/graphql, solo lectura, sin sesión de usuario.
Cinemex: precios y plano desde GET sessions/{id}, público y sin abrir orden de checkout (verificado 2026-09-25; hasta
ese día el plano se leía con POST buy/selectTickets, que abre una orden en Vista). El mismo plano da el aforo, la
asistencia final y la calibración del semáforo high/mid/low contra % vendido.
"""
import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import cinemex, cinepolis, config, plazas, store
from .http import ApiError, request_json
from .normalize import format_bucket

TZ = ZoneInfo(config.PILOT_TIMEZONE)
# Dulcería (config.CINEPOLIS_CONCESSIONS_URL): `cinema` es el vistaId; `menuType` no cambia la respuesta
# (probado con seis valores el 2026-09-08) y `userSession` acepta cualquier UUID.
MENU_QUERY = """query MenuByType($country: String!, $cinema: String!, $menuType: String!, $userSession: String!) {
  menuByType(country: $country, cinema: $cinema, menuType: $menuType, userSession: $userSession) {
    categories { name
      products { productName product active price productStructure productType tag promotionType qtyAvailable }
      subCategories { name
        products { productName product active price productStructure productType tag promotionType qtyAvailable } } } } }"""

SEATS_QUERY = """query Seats($countryId: String!, $sessionId: String!, $cinemaVistaId: String!) {
  seats(countryId: $countryId, sessionId: $sessionId, cinemaVistaId: $cinemaVistaId) {
    seatLayoutData { areas { description areaCategoryCode rowCount columnCount
      rows { physicalName seats { id status originalStatus seatStyle } } } } } }"""
TICKETS_QUERY = """query Tickets($countryId: String!, $sessionId: String!, $cinemaVistaId: String!) {
  tickets(countryId: $countryId, cinemaVistaId: $cinemaVistaId, sessionId: $sessionId) {
    areaCategoryCode tickets { id description ticketDescription priceInCents bookingFee type } } }"""

# Estados vistos en planos reales de Cinépolis (2026-09-08). "Broken" no se vende; Special y Companion sí.
NOT_SELLABLE = {"Broken"}
SOLD = {"Sold"}
TRANSIENT = ("(116)", "(101305)")   # Vista: "no es posible continuar por el momento"; suele pasar al reintentar


def log(msg):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(config.LOG_DIR / "sample.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def now_local():
    return datetime.now(TZ).replace(tzinfo=None)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _plaza_filter(chain, column="cinema_id", scope=config.SEATS_PLAZAS):
    """Cláusula `AND …` que deja solo las funciones de las plazas de `scope` (por defecto `config.SEATS_PLAZAS`; decisión
    2026-09-11: los planos no se censan a nivel nacional). `scope=None` no filtra: es la pasada nacional única de aforo,
    que se lanza a mano. Devuelve (sql, params); la membresía está en `scraper.plazas` y la geografía de cada cine en
    la tabla `cinema`."""
    if scope is None:
        return "", []
    keys = plazas.city_ids_for(scope, chain)
    if not keys:
        return " AND 0", []
    marks = ",".join("?" for _ in keys)
    return f" AND {column} IN (SELECT cinema_id FROM cinema WHERE chain = ? AND city_id IN ({marks}))", [chain, *keys]


def _scope_label(scope):
    return "nacional" if scope is None else ",".join(scope)


# --- Cinépolis --------------------------------------------------------------------------------------
def vista_ids(conn):
    """{slug: vistaId} de todos los cines de Cinépolis vistos en las capturas (tabla `cinema`)."""
    return {r[0]: r[1] for r in conn.execute("SELECT cinema_id, vista_id FROM cinema WHERE chain = 'cinepolis' AND vista_id IS NOT NULL")}


def seat_layout(session_id, vista_id, stats=None, attempts=3):
    """Plano de una función de Cinépolis: {seats, sold, broken, areas} o None si la API no lo tiene."""
    for i in range(attempts):
        try:
            data = cinepolis.gql(config.CINEPOLIS_TICKET_URL, SEATS_QUERY,
                                 {"countryId": config.CINEPOLIS_COUNTRY, "sessionId": str(session_id), "cinemaVistaId": vista_id}, stats)
            break
        except ApiError as e:
            if i + 1 < attempts and any(code in str(e) for code in TRANSIENT):
                time.sleep(config.SAMPLE_BACKOFF * (i + 1))
                continue
            raise
    layout = ((data.get("seats") or {}).get("seatLayoutData") or {})
    areas = layout.get("areas") or []
    if not areas:
        return None
    total = sold = broken = 0
    by_area = []
    for a in areas:
        st = Counter(s.get("status") for row in a.get("rows") or [] for s in row.get("seats") or [])
        n = sum(st.values())
        b = sum(v for k, v in st.items() if k in NOT_SELLABLE)
        s_ = sum(v for k, v in st.items() if k in SOLD)
        total += n; broken += b; sold += s_
        by_area.append({"area": a.get("description"), "code": a.get("areaCategoryCode"), "seats": n, "broken": b,
                        "sold": s_, "status": dict(st)})
    return {"seats": total - broken, "sold": sold, "broken": broken, "areas": by_area}


def cinepolis_menu(vista_id, stats=None):
    """Menú de dulcería de un cine de Cinépolis: lista plana de productos con categoría y precio en centavos."""
    import uuid
    data = cinepolis.gql(config.CINEPOLIS_CONCESSIONS_URL, MENU_QUERY, {"country": config.CINEPOLIS_COUNTRY, "cinema": str(vista_id),
                                                       "menuType": "SOLO_ALIMENTOS", "userSession": str(uuid.uuid4())}, stats)
    out = []
    for cat in (data.get("menuByType") or {}).get("categories") or []:
        groups = [("", cat.get("products") or [])] + [(sc.get("name") or "", sc.get("products") or []) for sc in cat.get("subCategories") or []]
        for sub, prods in groups:
            for p in prods:
                out.append({"category": (cat.get("name") or "").strip(), "sub_category": sub.strip(), "product_id": str(p.get("product") or ""),
                            "product_name": (p.get("productName") or "").strip(), "price_cents": p.get("price"),
                            "product_structure": p.get("productStructure"), "promotion_type": p.get("promotionType"),
                            "active": 1 if p.get("active") else 0})
    return out


def cinepolis_tickets(session_id, vista_id, stats=None):
    data = cinepolis.gql(config.CINEPOLIS_TICKET_URL, TICKETS_QUERY,
                         {"countryId": config.CINEPOLIS_COUNTRY, "sessionId": str(session_id), "cinemaVistaId": vista_id}, stats)
    out = []
    for area in data.get("tickets") or []:
        for t in area.get("tickets") or []:
            out.append({"name": t.get("description") or t.get("ticketDescription"), "cents": t.get("priceInCents"),
                        "fee": t.get("bookingFee"), "type": t.get("type"), "area": area.get("areaCategoryCode")})
    return out


# --- Cinemex ------------------------------------------------------------------------------------------
def cinemex_tickets(session_id, stats=None):
    d = cinemex.get(f"sessions/{session_id}", stats=stats)
    return [{"name": t.get("name"), "cents": t.get("price"), "fee": t.get("fee"), "type": t.get("cat"),
             "regular": bool((t.get("extra") or {}).get("regular"))} for t in d.get("tickets") or []]


# Estados del plano de Cinemex: "E" hueco del plano (`type: blank`), "0" disponible, "1" vendido.
def cinemex_layout(session_id, stats=None):
    """Plano de una función de Cinemex desde `GET sessions/{id}`, público y sin abrir orden de checkout (verificado
    2026-09-25: el `layout` es el mismo que devolvía `buy/selectTickets` y sigue respondiendo después del inicio).
    Devuelve {seats, sold, broken, areas}; `ApiError` si la sesión ya no trae plano, porque eso significaría que
    Cinemex lo quitó del GET y el muestreo entero deja de ser válido."""
    sess = cinemex.get(f"sessions/{session_id}", stats=stats)
    layout = sess.get("layout")
    if layout is None:
        raise ApiError(f"sessions/{session_id} sin layout: Cinemex pudo quitar el plano del GET público")
    if not layout:
        return None
    total = sold = 0
    by_area = []
    for sec in layout:
        st = Counter(x.get("status") for x in sec.get("seats") or [])
        n = st.get("0", 0) + st.get("1", 0)
        total += n; sold += st.get("1", 0)
        by_area.append({"area": sec.get("name"), "seats": n, "sold": st.get("1", 0), "status": dict(st)})
    return {"seats": total, "sold": sold, "broken": 0, "areas": by_area}


# --- Cineteca Nacional ---------------------------------------------------------------------------------
# La Cineteca corre sobre Vista (como Cinépolis) pero se lee directo de su Connect API con el token embebido en su app
# (config.CINETECA_CONNECT_TOKEN). El plano trae la sala en `Areas[].Description`. Semántica de estado (PENDIENTE
# confirmar contra una función llena, 2026-09-26: la primera lectura salía todo en 0): `OriginalStatus` es el estado
# físico de la butaca (≠ 0 = no vendible: rota/casa) y `Status` el estado en vivo (≠ 0 en una butaca vendible = ocupada).
# Se guarda el histograma completo de ambos en `areas_json`, así el reparto exacto se recalcula sin volver a pedir.
def cineteca_layout(session_id, cinema_code, stats=None):
    """Plano de una función de la Cineteca desde el Connect API de Vista (RESTData.svc, solo lectura, sin abrir orden).
    Devuelve {seats, sold, broken, areas, screen} o None si la función no tiene plano."""
    url = f"{config.CINETECA_VISTA_BASE_URL}/RESTData.svc/cinemas/{cinema_code}/sessions/{session_id}/seat-plan"
    data = request_json(url, headers={"connectapitoken": config.CINETECA_CONNECT_TOKEN})
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    areas = ((data.get("SeatLayoutData") or {}).get("Areas")) or []
    if not areas:
        return None
    total = sold = broken = 0
    by_area = []
    for a in areas:
        seats = [s for row in a.get("Rows") or [] for s in row.get("Seats") or []]
        b = sum(1 for s in seats if s.get("OriginalStatus") not in (0, None))
        so = sum(1 for s in seats if s.get("OriginalStatus") in (0, None) and s.get("Status") not in (0, None))
        total += len(seats); broken += b; sold += so
        by_area.append({"area": a.get("Description"), "code": a.get("AreaCategoryCode"), "seats": len(seats) - b,
                        "broken": b, "sold": so,
                        "status": dict(Counter(s.get("Status") for s in seats)),
                        "original_status": dict(Counter(s.get("OriginalStatus") for s in seats))})
    return {"seats": total - broken, "sold": sold, "broken": broken, "areas": by_area,
            "screen": by_area[0]["area"] if by_area else None}


def layout_for(chain, row, vids, stats):
    """Plano según la cadena. Cinépolis: sesión + vistaId; Cinemex: id de sesión nacional; Cineteca: sesión + sede."""
    if chain == "cinepolis":
        vid = vids.get(row["cinema_id"])
        if not vid:
            raise ApiError(f"sin vistaId para {row['cinema_id']}")
        return seat_layout(row["show_id"].rsplit(":", 1)[1], vid, stats)
    if chain == "cineteca":
        return cineteca_layout(row["show_id"].rsplit(":", 1)[1], row["cinema_id"], stats)
    return cinemex_layout(row["show_id"], stats)


# --- precios --------------------------------------------------------------------------------------------
def day_type_of(iso_date):
    """weekend (vie–dom) | promo (mar y mié: días de precio reducido en ambas cadenas) | weekday (lun y jue)."""
    wd = datetime.fromisoformat(iso_date).weekday()
    return "weekend" if wd >= 4 else "promo" if wd in (1, 2) else "weekday"


def summarize_prices(tickets):
    """(general, min, max, fee) en centavos. 'General' = boleto adulto regular sin promoción."""
    priced = [t for t in tickets if isinstance(t.get("cents"), int) and t["cents"] > 0]
    if not priced:
        return None, None, None, None
    general = None
    for t in priced:
        name = (t.get("name") or "").lower()
        if t.get("regular") or "general" in name or "adulto" in name or "estreno" in name:
            general = t["cents"]; break
    general = general or max(t["cents"] for t in priced)
    return general, min(t["cents"] for t in priced), max(t["cents"] for t in priced), priced[0].get("fee") or 0


# --- pasadas -------------------------------------------------------------------------------------------
CAPACITY_CANDIDATES = 3   # funciones distintas a probar por sala si la primera ya no existe (404 / 101)


def _measure_screen(chain, key, candidates, vids, stats):
    """Plano de una sala probando sus funciones en orden. Devuelve (key, plano | None, función usada, último error).
    Solo red: corre en un hilo del pase de aforo."""
    lay, last_err, used = None, None, None
    for r in candidates:
        try:
            lay = layout_for(chain, r, vids, stats)
        except ApiError as e:
            last_err = e
            time.sleep(config.SAMPLE_BACKOFF)
            continue
        time.sleep(config.SAMPLE_PAUSE)
        if lay:
            used = r; break
    return key, lay, used, last_err


def capacity_pass(conn, chain="cinepolis", refresh=False, dry_run=False, limit=None, scope=config.SEATS_PLAZAS, workers=None):
    """Un plano por (cine, sala). Prueba hasta CAPACITY_CANDIDATES funciones futuras de la sala, de la
    más próxima en adelante, porque el snapshot puede listar funciones que la cadena ya retiró. `scope=None` recorre
    todos los cines capturados: la pasada nacional única que deja consultables salas y butacas de todo el país.
    `workers` hilos piden planos a la vez (por defecto `config.SAMPLE_WORKERS`); la base se escribe en este hilo."""
    stats = {"calls": 0}   # contador aproximado con varios hilos: solo informa
    vids = vista_ids(conn) if chain == "cinepolis" else {}
    now = now_local().strftime("%Y-%m-%dT%H:%M:%S")
    scope_sql, scope_params = _plaza_filter(chain, scope=scope)
    rows = conn.execute(f"""
        SELECT cinema_id, screen, show_id, datetime_local FROM current_showtime
        WHERE chain = ? AND datetime_local >= ?{scope_sql} ORDER BY cinema_id, screen, datetime_local""", (chain, now, *scope_params)).fetchall()
    by_screen = {}
    for r in rows:
        by_screen.setdefault((r["cinema_id"], r["screen"]), []).append(r)
    have = {(r["cinema_id"], r["screen"]) for r in conn.execute("SELECT cinema_id, screen FROM auditorium WHERE chain = ?", (chain,))}
    todo = [k for k in by_screen if refresh or k not in have]
    if limit:
        todo = todo[:limit]
    workers = workers or config.SAMPLE_WORKERS
    log(f"capacity {chain} [{_scope_label(scope)}]: {len(by_screen)} salas con funciones, {len(todo)} por muestrear, "
        f"{workers} hilo(s){' (dry-run)' if dry_run else ''}")
    ok = fail = 0
    if dry_run:
        todo = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda key: _measure_screen(chain, key, by_screen[key][:CAPACITY_CANDIDATES], vids, stats), todo)
        for key, lay, used, last_err in results:
            if not lay:
                fail += 1
                log(f"capacity FAIL {chain} {key[0]} sala {key[1]}: {last_err or 'sin plano'}"[:300])
                continue
            session_id = used["show_id"].rsplit(":", 1)[-1]
            conn.execute("""INSERT OR REPLACE INTO auditorium (chain, cinema_id, screen, seats, broken, areas_json, session_id, sampled_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                         (chain, key[0], key[1], lay["seats"], lay["broken"], json.dumps(lay["areas"], ensure_ascii=False), session_id, utc_now()))
            conn.commit(); ok += 1
    log(f"capacity {chain} ok={ok} fail={fail} calls={stats['calls']}")
    return fail == 0


CALIBRATION_LEVELS = ("high", "mid", "low")   # semáforo de Cinemex


def calibration_progress(conn, chain="cinemex"):
    """Muestras de ocupación por nivel del semáforo ya guardadas para la cadena: el estado de la calibración."""
    return Counter(r[0] for r in conn.execute(
        "SELECT COALESCE(availability, '') FROM occupancy_sample WHERE chain = ?", (chain,)))


def occupancy_pass(conn, chain="cinepolis", lead=60, tolerance=15, dry_run=False, limit=None, per_level=None, scope=config.SEATS_PLAZAS):
    """Plano de cada función que empieza en [lead−tol, lead+tol] minutos y aún no se muestreó en esa ventana.
    Con `per_level` toma como mucho N funciones por nivel de `availability` (calibración del semáforo)."""
    stats = {"calls": 0}
    now = now_local()
    lo, hi = now + timedelta(minutes=lead - tolerance), now + timedelta(minutes=lead + tolerance)
    scope_sql, scope_params = _plaza_filter(chain, "s.cinema_id", scope)
    rows = conn.execute(f"""
        SELECT s.* FROM current_showtime s
        WHERE s.chain = ? AND s.datetime_local BETWEEN ? AND ?{scope_sql}
          AND NOT EXISTS (SELECT 1 FROM occupancy_sample o WHERE o.chain = s.chain AND o.show_id = s.show_id
                          AND o.minutes_to_start BETWEEN ? AND ?)
        ORDER BY s.datetime_local""", (chain, lo.strftime("%Y-%m-%dT%H:%M:%S"), hi.strftime("%Y-%m-%dT%H:%M:%S"), *scope_params,
                                        lead - tolerance - 5, lead + tolerance + 5)).fetchall()
    if per_level:
        have = calibration_progress(conn, chain)
        picked, count = [], Counter()
        for r in rows:
            lvl = r["availability"] or ""
            if have[lvl] + count[lvl] < per_level:
                picked.append(r); count[lvl] += 1
        rows = picked
        # Estado de la calibración antes de este chunk: cada plano se guarda con su propio commit, así que si la
        # corrida se cae, la siguiente parte de aquí.
        log(f"calibración {chain}: muestras por nivel {dict(have)} de {per_level}; faltan "
            f"{ {lvl: max(per_level - have[lvl], 0) for lvl in CALIBRATION_LEVELS} }")
    if limit:
        rows = rows[:limit]
    levels = f" por nivel {dict(Counter(r['availability'] or '' for r in rows))}" if per_level else ""
    log(f"occupancy {chain} [{_scope_label(scope)}]: {len(rows)} funciones entre {lo:%H:%M} y {hi:%H:%M}{levels}{' (dry-run)' if dry_run else ''}")
    if not rows or dry_run:
        return True
    return _take_layouts(conn, chain, rows, stats, "occupancy")


def post_start_pass(conn, chain="cinepolis", after=config.POST_START_AFTER_MIN, tolerance=config.POST_START_TOLERANCE_MIN, dry_run=False, limit=None,
                    scope=config.SEATS_PLAZAS):
    """Plano de cada función que empezó hace [after−tol, after+tol] minutos y aún no tiene muestra post-inicio.

    Es la asistencia final (la venta sigue creciendo después del arranque: prueba del 2026-09-08, de 2 a 6
    veces lo vendido a T−60) y por eso el target del modelo de consumo. Cinépolis retira la función de la
    cartelera al empezar, así que ya no está en `current_showtime`: los candidatos salen de la unión de
    `current_showtime` (Cinemex la conserva ~2.5 h) y de las funciones ya muestreadas a T−60. El plano de
    Cinépolis sigue disponible al menos 150 min después del inicio. `minutes_to_start` queda negativo."""
    stats = {"calls": 0}
    now = now_local()
    lo, hi = now - timedelta(minutes=after + tolerance), now - timedelta(minutes=after - tolerance)
    w = (lo.strftime("%Y-%m-%dT%H:%M:%S"), hi.strftime("%Y-%m-%dT%H:%M:%S"))
    scope_sql, scope_params = _plaza_filter(chain, scope=scope)
    rows = conn.execute(f"""
        SELECT chain, show_id, cinema_id, screen, movie_id, movie_title, datetime_local, availability
        FROM current_showtime WHERE chain = ? AND datetime_local BETWEEN ? AND ?{scope_sql}
        UNION
        SELECT chain, show_id, cinema_id, screen, movie_id, movie_title, datetime_local, availability
        FROM occupancy_sample WHERE chain = ? AND datetime_local BETWEEN ? AND ? AND minutes_to_start >= 0{scope_sql}
        ORDER BY datetime_local""", (chain, *w, *scope_params, chain, *w, *scope_params)).fetchall()
    done = {r[0] for r in conn.execute(
        "SELECT show_id FROM occupancy_sample WHERE chain = ? AND minutes_to_start < 0 AND datetime_local BETWEEN ? AND ?",
        (chain, *w))}
    seen, picked = set(), []
    for r in rows:
        if r["show_id"] in done or r["show_id"] in seen:
            continue
        seen.add(r["show_id"]); picked.append(r)
    if limit:
        picked = picked[:limit]
    log(f"post-start {chain} [{_scope_label(scope)}]: {len(picked)} funciones iniciadas entre {lo:%H:%M} y {hi:%H:%M}{' (dry-run)' if dry_run else ''}")
    if not picked or dry_run:
        return True
    return _take_layouts(conn, chain, picked, stats, "post-start")


def _take_layouts(conn, chain, rows, stats, label):
    """Pide el plano de cada función y guarda una fila en occupancy_sample (y el aforo de la sala si falta)."""
    vids = vista_ids(conn) if chain == "cinepolis" else {}
    ok = fail = 0
    for r in rows:
        try:
            lay = layout_for(chain, r, vids, stats)
        except ApiError as e:
            fail += 1; log(f"{label} FAIL {chain} {r['show_id']}: {e}"[:300])
            time.sleep(config.SAMPLE_BACKOFF); continue
        time.sleep(config.SAMPLE_PAUSE)
        if not lay:
            fail += 1; continue
        # La Cineteca no publica la sala en la cartelera: llega en el plano (`Areas[].Description`).
        screen = r["screen"] or lay.get("screen")
        starts = datetime.fromisoformat(r["datetime_local"])
        mins = int(round((starts - now_local()).total_seconds() / 60))
        pct = round(100.0 * lay["sold"] / lay["seats"], 1) if lay["seats"] else None
        conn.execute("""INSERT INTO occupancy_sample (chain, show_id, cinema_id, screen, movie_id, movie_title, datetime_local,
                            sampled_at, minutes_to_start, seats, sold, broken, sold_pct, availability)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (chain, r["show_id"], r["cinema_id"], screen, r["movie_id"], r["movie_title"], r["datetime_local"],
                      utc_now(), mins, lay["seats"], lay["sold"], lay["broken"], pct, r["availability"]))
        # de paso, el aforo de la sala si aún no lo tenemos
        conn.execute("""INSERT OR IGNORE INTO auditorium (chain, cinema_id, screen, seats, broken, areas_json, session_id, sampled_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                     (chain, r["cinema_id"], screen, lay["seats"], lay["broken"], json.dumps(lay["areas"], ensure_ascii=False),
                      r["show_id"].rsplit(":", 1)[-1], utc_now()))
        conn.commit(); ok += 1
    log(f"{label} {chain} ok={ok} fail={fail} calls={stats['calls']}")
    return fail == 0


def price_pass(conn, days=7, limit=None, dry_run=False):
    """Una función por (cadena, cine, cubeta de formato, tipo de día) sin muestra en los últimos `days` días."""
    stats = {"calls": 0}
    now = now_local()
    rows = conn.execute("""SELECT * FROM current_showtime WHERE datetime_local >= ? AND date <= ? ORDER BY datetime_local""",
                        (now.strftime("%Y-%m-%dT%H:%M:%S"), (now + timedelta(days=days)).strftime("%Y-%m-%d"))).fetchall()
    recent = {(r["chain"], r["cinema_id"], r["format_bucket"], r["day_type"]) for r in conn.execute(
        "SELECT chain, cinema_id, format_bucket, day_type FROM price_sample WHERE sampled_at >= ?",
        ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds"),))}
    todo = {}
    for r in rows:
        d = dict(r)
        title = (d.get("movie_title") or "").lower()
        if title.startswith("evento") or "matinee" in title or "matiné" in title:
            continue   # los eventos tienen precios propios; no representan al cine
        key = (d["chain"], d["cinema_id"], format_bucket(d), day_type_of(d["date"]))
        if key in recent or key in todo:
            continue
        todo[key] = d
    items = list(todo.items())
    if limit:
        items = items[:limit]
    log(f"prices: {len(todo)} combinaciones pendientes, {len(items)} en esta pasada{' (dry-run)' if dry_run else ''}")
    if dry_run:
        return True
    vids = vista_ids(conn) if any(k[0] == "cinepolis" for k, _ in items) else {}
    ok = fail = 0
    for (chain, cinema_id, bucket, day_type), r in items:
        try:
            if chain == "cinepolis":
                tickets = cinepolis_tickets(r["show_id"].rsplit(":", 1)[1], vids[cinema_id], stats)
            else:
                tickets = cinemex_tickets(r["show_id"], stats)
        except (ApiError, KeyError) as e:
            fail += 1; log(f"prices FAIL {chain} {r['show_id']}: {e}"[:300]); continue
        general, lo, hi, fee = summarize_prices(tickets)
        if general is None:
            log(f"prices skip {chain} {r['show_id']}: sin boletos"); continue   # se reintenta en la siguiente pasada
        conn.execute("""INSERT INTO price_sample (chain, show_id, cinema_id, screen, format_bucket, day_type, date, datetime_local,
                            sampled_at, general_cents, min_cents, max_cents, fee_cents, tickets_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (chain, r["show_id"], cinema_id, r["screen"], bucket, day_type, r["date"], r["datetime_local"],
                      utc_now(), general, lo, hi, fee, json.dumps(tickets, ensure_ascii=False)))
        conn.commit(); ok += 1
    log(f"prices ok={ok} fail={fail} calls={stats['calls']}")
    return fail == 0


def concessions_pass(conn, chain="cinepolis", days=config.CONCESSIONS_REFRESH_DAYS, limit=None, dry_run=False):
    """Menú de dulcería completo por cine, renovado cada `days` días. Solo Cinépolis: Cinemex tiene la venta en
    línea apagada (`candybar=false` en sus 278 cines el 2026-09-08) y sus precios llegarán del cliente."""
    if chain != "cinepolis":
        log(f"concessions: {chain} no expone dulcería por API"); return True
    stats = {"calls": 0}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    recent = {r[0] for r in conn.execute("SELECT DISTINCT cinema_id FROM concession_price WHERE chain = ? AND sampled_at >= ?", (chain, since))}
    vids = vista_ids(conn)
    todo = [(slug, vid) for slug, vid in sorted(vids.items()) if slug not in recent]
    if limit:
        todo = todo[:limit]
    log(f"concessions {chain}: {len(todo)} cines pendientes de {len(vids)}{' (dry-run)' if dry_run else ''}")
    if dry_run or not todo:
        return True
    ok = fail = 0
    for slug, vid in todo:
        try:
            items = cinepolis_menu(vid, stats)
        except ApiError as e:
            fail += 1; log(f"concessions FAIL {slug}: {e}"[:300]); time.sleep(config.SAMPLE_BACKOFF); continue
        time.sleep(config.SAMPLE_PAUSE)
        if not items:
            log(f"concessions skip {slug}: menú vacío"); continue
        ts = utc_now()
        conn.executemany("""INSERT INTO concession_price (chain, cinema_id, sampled_at, category, sub_category, product_id, product_name,
                                price_cents, product_structure, promotion_type, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         [(chain, slug, ts, i["category"], i["sub_category"], i["product_id"], i["product_name"], i["price_cents"],
                           i["product_structure"], i["promotion_type"], i["active"]) for i in items])
        conn.commit(); ok += 1
    log(f"concessions {chain} ok={ok} fail={fail} calls={stats['calls']}")
    return fail == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capacity", action="store_true")
    ap.add_argument("--occupancy", action="store_true")
    ap.add_argument("--post-start", action="store_true", help="planos de funciones ya iniciadas (asistencia final)")
    ap.add_argument("--prices", action="store_true")
    ap.add_argument("--concessions", action="store_true", help="menú de dulcería con precios por cine (Cinépolis)")
    ap.add_argument("--chain", choices=["cinepolis", "cinemex", "cineteca"], default="cinepolis",
                    help="cadena para --capacity / --occupancy / --post-start (los precios siempre son de ambas)")
    ap.add_argument("--per-level", type=int, help="occupancy: calibración, máximo N funciones por nivel del semáforo")
    ap.add_argument("--lead", type=int, default=60, help="minutos antes de la función (ocupación)")
    ap.add_argument("--tolerance", type=int, default=None, help="ocupación: ±min (15 con --lead, config.POST_START_TOLERANCE_MIN con --after)")
    ap.add_argument("--after", type=int, default=config.POST_START_AFTER_MIN, help="post-start: minutos después del inicio (ventana ±tolerance)")
    ap.add_argument("--refresh", action="store_true", help="capacity: volver a medir salas ya conocidas")
    ap.add_argument("--plazas", default=None,
                    help="planos: plazas a recorrer separadas por coma, o 'all' para todos los cines capturados (por defecto AC_SEATS_PLAZAS)")
    ap.add_argument("--workers", type=int, default=None, help="capacity: hilos que piden planos a la vez (por defecto AC_SAMPLE_WORKERS)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not (a.capacity or a.occupancy or a.post_start or a.prices or a.concessions):
        ap.error("indica --capacity, --occupancy, --post-start, --prices y/o --concessions")
    scope = config.SEATS_PLAZAS if a.plazas is None else (None if a.plazas.strip().lower() == "all" else tuple(p.strip() for p in a.plazas.split(",") if p.strip()))
    conn = store.connect()
    ok = True
    t0 = time.time()
    if a.capacity:
        ok &= capacity_pass(conn, chain=a.chain, refresh=a.refresh, dry_run=a.dry_run, limit=a.limit, scope=scope, workers=a.workers)
    if a.occupancy:
        ok &= occupancy_pass(conn, chain=a.chain, lead=a.lead, tolerance=a.tolerance or 15, dry_run=a.dry_run,
                             limit=a.limit, per_level=a.per_level, scope=scope)
    if a.post_start:
        ok &= post_start_pass(conn, chain=a.chain, after=a.after, tolerance=a.tolerance or config.POST_START_TOLERANCE_MIN, dry_run=a.dry_run,
                              limit=a.limit, scope=scope)
    if a.prices:
        ok &= price_pass(conn, limit=a.limit, dry_run=a.dry_run)
    if a.concessions:
        ok &= concessions_pass(conn, chain=a.chain, limit=a.limit, dry_run=a.dry_run)
    conn.close()
    log(f"done in {time.time() - t0:.0f}s ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
