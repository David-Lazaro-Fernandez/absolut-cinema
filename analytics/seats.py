"""Butacas, ocupación y precios a partir de las tablas de muestreo (scraper/sample.py).
Cinépolis tiene aforo por sala desde los planos; Cinemex lo tendrá del cliente."""
from datetime import datetime, timedelta, timezone

from scraper.normalize import norm_title
from scraper.titles import title_key

from .db import rows
from .labels import SLOTS
from .plaza import plaza_cinema_where
from .queries import _FORMAT_CASE, _HOUR, _SLOT_CASE, _window

# Tipo de día del muestreo de precios (scraper.sample.day_type_of), en SQL: vie–dom, mar–mié con precio reducido, lun y jue.
_DAY_TYPE_CASE = """CASE WHEN strftime('%w', date) IN ('5', '6', '0') THEN 'weekend'
                         WHEN strftime('%w', date) IN ('2', '3') THEN 'promo' ELSE 'weekday' END"""


def capacity_summary(conn, plaza=None):
    """Por cadena: cines y salas con aforo conocido, butacas totales y tamaño de sala."""
    where, params = plaza_cinema_where(plaza)
    return rows(conn, f"""
        SELECT chain, COUNT(DISTINCT cinema_id) cinemas, COUNT(*) screens, SUM(seats) seats,
               ROUND(AVG(seats)) avg_seats, MIN(seats) min_seats, MAX(seats) max_seats,
               SUM(seats < 80) small, SUM(seats BETWEEN 80 AND 149) medium,
               SUM(seats BETWEEN 150 AND 249) large, SUM(seats >= 250) xlarge, MAX(sampled_at) sampled_at
        FROM auditorium WHERE 1 = 1{where} GROUP BY chain ORDER BY chain""", params)


def capacity_by_cinema(conn, chain="cinepolis", plaza=None):
    """Salas y butacas por complejo, con el nombre del cine y cuántas salas programan hoy."""
    where, params = plaza_cinema_where(plaza, "a.", chains=(chain,))
    return rows(conn, f"""
        SELECT a.cinema_id, COALESCE(c.name, a.cinema_id) cinema_name, COUNT(*) screens, SUM(a.seats) seats,
               ROUND(AVG(a.seats)) avg_seats, MIN(a.seats) min_seats, MAX(a.seats) max_seats
        FROM auditorium a LEFT JOIN cinema c ON c.chain = a.chain AND c.cinema_id = a.cinema_id
        WHERE a.chain = ?{where} GROUP BY a.cinema_id ORDER BY seats DESC""", (chain, *params))


def offered_seats(conn, d0=None, d1=None, from_now=True, hours=None, plaza=None):
    """Butacas ofertadas en la ventana = funciones × aforo de su sala, por cadena, y qué parte de las
    funciones tiene aforo conocido. Solo suma las funciones con sala conocida."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, plaza=plaza, alias="s.")
    return rows(conn, f"""
        SELECT s.chain, COUNT(*) shows, SUM(a.seats IS NOT NULL) shows_with_capacity,
               ROUND(100.0 * SUM(a.seats IS NOT NULL) / COUNT(*), 1) pct_known,
               SUM(a.seats) seats_offered, ROUND(AVG(a.seats)) avg_seats_per_show,
               COUNT(DISTINCT s.date) days, COUNT(DISTINCT s.cinema_id) cinemas
        FROM current_showtime s
        LEFT JOIN auditorium a ON a.chain = s.chain AND a.cinema_id = s.cinema_id AND a.screen = s.screen
        WHERE {where} GROUP BY s.chain ORDER BY s.chain""", params)


def offered_by_title(conn, d0=None, d1=None, from_now=True, limit=15, chain="cinepolis", hours=None, plaza=None):
    """Share de butacas ofertadas por título frente a share de funciones (solo cadenas con aforo)."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, plaza=plaza, alias="s.", chains=(chain,))
    return rows(conn, f"""
        WITH base AS (
          SELECT title_key(s.title_norm) title_norm, s.movie_title, a.seats
          FROM current_showtime s
          JOIN auditorium a ON a.chain = s.chain AND a.cinema_id = s.cinema_id AND a.screen = s.screen
          WHERE {where} AND s.chain = ?),
        tot AS (SELECT COUNT(*) n, SUM(seats) seats FROM base)
        SELECT title_norm, MAX(movie_title) title, COUNT(*) shows, SUM(seats) seats,
               ROUND(100.0 * COUNT(*) / (SELECT n FROM tot), 1) share_shows,
               ROUND(100.0 * SUM(seats) / (SELECT seats FROM tot), 1) share_seats,
               ROUND(AVG(seats)) avg_seats
        FROM base GROUP BY title_norm ORDER BY seats DESC LIMIT ?""", params + [chain, limit])


# Fase de la muestra: "post" = tras el inicio (asistencia final, lo que se mide cada hora); "pre" = preventa a T−60.
_PHASE = {"post": "minutes_to_start < 0", "pre": "minutes_to_start >= 0", "all": "1 = 1"}


def occupancy_summary(conn, chain="cinepolis", phase="post", plaza=None):
    """Muestras de ocupación acumuladas por color del semáforo: cuántas, % vendido medio, mínimo y máximo.
    `phase`: post (asistencia final, por defecto), pre (preventa a T−60) o all."""
    where, params = plaza_cinema_where(plaza, chains=(chain,))
    return rows(conn, f"""
        SELECT COALESCE(NULLIF(availability, ''), '(sin color)') availability, COUNT(*) samples,
               ROUND(AVG(sold_pct), 1) avg_sold_pct, MIN(sold_pct) min_sold_pct, MAX(sold_pct) max_sold_pct,
               SUM(sold) sold, SUM(seats) seats
        FROM occupancy_sample WHERE chain = ? AND {_PHASE[phase]}{where} GROUP BY 1 ORDER BY avg_sold_pct DESC""", (chain, *params))


def occupancy_recent(conn, limit=50, chain="cinepolis", phase="post", plaza=None):
    """Últimas muestras de ocupación de la cadena, con cine, función y % vendido."""
    where, params = plaza_cinema_where(plaza, "o.", chains=(chain,))
    return rows(conn, f"""
        SELECT o.sampled_at, COALESCE(c.name, o.cinema_id) cinema_name, o.screen, o.movie_title, o.datetime_local,
               o.minutes_to_start, o.seats, o.sold, o.sold_pct, o.availability
        FROM occupancy_sample o LEFT JOIN cinema c ON c.chain = o.chain AND c.cinema_id = o.cinema_id
        WHERE o.chain = ? AND {_PHASE[phase]}{where} ORDER BY o.id DESC LIMIT ?""", (chain, *params, limit))


def occupancy_by_cinema(conn, days=7, chain="cineteca", phase="post", plaza=None):
    """Ocupación por complejo y franja según los planos de los últimos `days` días (sin la cartelera: la sala sale del
    plano). Por fila: `cinema_id`, `cinema_name`, `slot` (clave de `labels.SLOTS`), `samples`, `seats` (butacas
    medidas) y `sold_pct` (% vendido ponderado por aforo). Orden: complejo y franja en el orden del día."""
    where, params = plaza_cinema_where(plaza, "o.", chains=(chain,))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    return rows(conn, f"""
        SELECT o.cinema_id, COALESCE(MAX(c.name), o.cinema_id) cinema_name, {_SLOT_CASE} slot,
               COUNT(*) samples, SUM(o.seats) seats, ROUND(100.0 * SUM(o.sold) / SUM(o.seats), 1) sold_pct
        FROM occupancy_sample o LEFT JOIN cinema c ON c.chain = o.chain AND c.cinema_id = o.cinema_id
        WHERE o.chain = ? AND {_PHASE[phase]} AND o.seats > 0
          AND o.sold IS NOT NULL AND o.sampled_at >= ?{where}
        GROUP BY o.cinema_id, slot ORDER BY o.cinema_id, MIN({_HOUR})""",
                (chain, since, *params))


def prices(conn, days=14, plaza=None):
    """Precio de boleto general (mediana, mínimo y máximo) por cadena, cubeta de formato y tipo de día,
    sobre las muestras de los últimos `days` días, con la fecha de la muestra más reciente (`last_sampled`)."""
    where, params = plaza_cinema_where(plaza)
    return rows(conn, f"""
        WITH p AS (SELECT chain, format_bucket, day_type, general_cents, cinema_id, sampled_at
                   FROM price_sample WHERE general_cents IS NOT NULL
                     AND sampled_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ? || ' days'){where}),
             ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY chain, format_bucket, day_type ORDER BY general_cents) rk,
                               COUNT(*) OVER (PARTITION BY chain, format_bucket, day_type) n FROM p)
        SELECT chain, format_bucket, day_type, MAX(n) samples, COUNT(DISTINCT cinema_id) cinemas,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN general_cents END) / 100.0, 0) median_price,
               MIN(general_cents) / 100.0 min_price, MAX(general_cents) / 100.0 max_price, MAX(sampled_at) last_sampled
        FROM ranked GROUP BY chain, format_bucket, day_type ORDER BY chain, format_bucket, day_type""", (f"-{int(days)}", *params))


def effective_ticket_price(conn, d0=None, d1=None, from_now=True, hours=None, plaza=None, days=14):
    """Boleto promedio de cada cadena en la ventana: la mediana del boleto general de cada formato y tipo de día
    (`prices`, últimos `days` días) ponderada por las funciones que la cadena programa en esa combinación. Es lo que
    cuesta en promedio una función de su cartelera. Por cadena: `shows`, `shows_priced`, `pct_priced`, `avg_price`
    (None si ninguna función tiene precio) y `last_sampled`. Orden: cadena."""
    median = {(r["chain"], r["format_bucket"], r["day_type"]): r for r in prices(conn, days=days, plaza=plaza)}
    where, params, _ = _window(d0, d1, from_now, hours=hours, plaza=plaza)
    mix = rows(conn, f"""
        SELECT chain, {_FORMAT_CASE} format_bucket, {_DAY_TYPE_CASE} day_type, COUNT(*) shows
        FROM current_showtime WHERE {where} GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""", params)
    out = {}
    for r in mix:
        o = out.setdefault(r["chain"], {"chain": r["chain"], "shows": 0, "shows_priced": 0, "_amount": 0.0, "last_sampled": None})
        o["shows"] += r["shows"]
        p = median.get((r["chain"], r["format_bucket"], r["day_type"]))
        if p and p["median_price"]:
            o["shows_priced"] += r["shows"]
            o["_amount"] += r["shows"] * p["median_price"]
            o["last_sampled"] = max(o["last_sampled"] or "", p["last_sampled"])
    for o in out.values():
        amount = o.pop("_amount")
        o["pct_priced"] = round(100.0 * o["shows_priced"] / o["shows"], 1) if o["shows"] else 0.0
        o["avg_price"] = round(amount / o["shows_priced"], 1) if o["shows_priced"] else None
    return [out[c] for c in sorted(out)]


def occupancy_by_title(conn, days=7, chain="cinepolis", min_samples=20, plaza=None):
    """Demanda por título según los planos tras el inicio de los últimos `days` días: % de butacas vendidas y el que
    se esperaría por su horario (promedio de la cadena en la misma franja y tipo de día), y su cociente
    (`demand_index`: 1 = lo normal para su horario, 1.5 = vende 50 % más). Así un título programado de noche no
    parece más demandado solo por su hora. Por título normalizado con al menos `min_samples` funciones: `title_norm`,
    `title`, `samples`, `sold_pct`, `expected_pct`, `demand_index`, `last_sampled`. Orden: `demand_index` desc."""
    where, params = plaza_cinema_where(plaza, chains=(chain,))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    samples = rows(conn, f"""
        SELECT movie_title, datetime_local, date(datetime_local) date, seats, sold, sampled_at
        FROM occupancy_sample WHERE chain = ? AND minutes_to_start < 0 AND seats > 0 AND sold IS NOT NULL
          AND sampled_at >= ?{where} ORDER BY id""", (chain, since, *params))
    if not samples:
        return []

    def cell(r):
        hour = int(r["datetime_local"][11:13])
        weekend = datetime.fromisoformat(r["date"]).weekday() >= 4
        return next(k for k, lo, hi, _ in SLOTS if lo <= hour < hi), weekend

    by_cell = {}
    for r in samples:
        c = by_cell.setdefault(cell(r), [0, 0])
        c[0] += r["sold"]
        c[1] += r["seats"]
    by_title = {}
    for r in samples:
        sold, seats = by_cell[cell(r)]
        t = by_title.setdefault(title_key(norm_title(r["movie_title"])), {"title": r["movie_title"].strip(), "samples": 0, "sold": 0,
                                                               "seats": 0, "expected": 0.0, "last_sampled": ""})
        t["samples"] += 1
        t["sold"] += r["sold"]
        t["seats"] += r["seats"]
        t["expected"] += r["seats"] * sold / seats
        t["last_sampled"] = max(t["last_sampled"], r["sampled_at"])
    out = [{"title_norm": k, "title": t["title"], "samples": t["samples"],
            "sold_pct": round(100.0 * t["sold"] / t["seats"], 1),
            "expected_pct": round(100.0 * t["expected"] / t["seats"], 1),
            "demand_index": round(t["sold"] / t["expected"], 2) if t["expected"] else None,
            "last_sampled": t["last_sampled"]}
           for k, t in by_title.items() if t["samples"] >= min_samples]
    return sorted(out, key=lambda r: (-(r["demand_index"] or 0), r["title_norm"]))


def semaphore_calibration(conn, chain="cinemex", min_samples=5, plaza=None):
    """Qué % vendido corresponde a cada nivel del semáforo de una cadena, según las muestras de plano.
    Sirve para convertir el `availability` gratuito de cada snapshot en ocupación estimada."""
    where, params = plaza_cinema_where(plaza, chains=(chain,))
    return rows(conn, f"""
        SELECT COALESCE(NULLIF(availability, ''), '(sin color)') level, COUNT(*) samples,
               ROUND(100.0 * SUM(sold) / SUM(seats), 1) sold_pct,
               ROUND(AVG(sold_pct), 1) avg_sold_pct, MIN(sold_pct) min_sold_pct, MAX(sold_pct) max_sold_pct
        FROM occupancy_sample WHERE chain = ? AND seats > 0{where}
        GROUP BY 1 HAVING COUNT(*) >= ? ORDER BY sold_pct DESC""", (chain, *params, min_samples))


def estimated_occupancy(conn, d0=None, d1=None, from_now=True, chain="cinemex", min_samples=5, hours=None, plaza=None):
    """Butacas ocupadas estimadas en la ventana: aforo de la sala × % vendido calibrado del nivel de
    semáforo de cada función. Solo funciones con aforo conocido y nivel calibrado. La calibración del semáforo
    es nacional (el color significa lo mismo en todos los cines); la ventana sí se acota a la plaza."""
    where, params, _ = _window(d0, d1, from_now, hours=hours, plaza=plaza, alias="s.", chains=(chain,))
    return rows(conn, f"""
        WITH cal AS (SELECT COALESCE(NULLIF(availability, ''), '(sin color)') level,
                            100.0 * SUM(sold) / SUM(seats) sold_pct, COUNT(*) n
                     FROM occupancy_sample WHERE chain = ? AND seats > 0 GROUP BY 1 HAVING COUNT(*) >= ?)
        SELECT s.chain, COUNT(*) shows, SUM(a.seats IS NOT NULL AND c.level IS NOT NULL) shows_estimated,
               SUM(a.seats) seats_offered, ROUND(SUM(a.seats * c.sold_pct / 100.0)) seats_occupied_est,
               ROUND(100.0 * SUM(a.seats * c.sold_pct / 100.0) / SUM(CASE WHEN c.level IS NOT NULL THEN a.seats END), 1) occupancy_pct_est
        FROM current_showtime s
        LEFT JOIN auditorium a ON a.chain = s.chain AND a.cinema_id = s.cinema_id AND a.screen = s.screen
        LEFT JOIN cal c ON c.level = COALESCE(NULLIF(s.availability, ''), '(sin color)')
        WHERE {where} AND s.chain = ? GROUP BY s.chain""", [chain, min_samples] + params + [chain])
