"""Butacas, ocupación y precios a partir de las tablas de muestreo (scraper/sample.py).
Cinépolis tiene aforo por sala desde los planos; Cinemex lo tendrá del cliente."""
from .db import rows
from .queries import _window


def capacity_summary(conn):
    """Por cadena: cines y salas con aforo conocido, butacas totales y tamaño de sala."""
    return rows(conn, """
        SELECT chain, COUNT(DISTINCT cinema_id) cinemas, COUNT(*) screens, SUM(seats) seats,
               ROUND(AVG(seats)) avg_seats, MIN(seats) min_seats, MAX(seats) max_seats,
               SUM(seats < 80) small, SUM(seats BETWEEN 80 AND 149) medium,
               SUM(seats BETWEEN 150 AND 249) large, SUM(seats >= 250) xlarge, MAX(sampled_at) sampled_at
        FROM auditorium GROUP BY chain ORDER BY chain""")


def capacity_by_cinema(conn, chain="cinepolis"):
    """Salas y butacas por complejo, con el nombre del cine y cuántas salas programan hoy."""
    return rows(conn, """
        SELECT a.cinema_id, COALESCE(c.cinema_name, a.cinema_id) cinema_name, COUNT(*) screens, SUM(a.seats) seats,
               ROUND(AVG(a.seats)) avg_seats, MIN(a.seats) min_seats, MAX(a.seats) max_seats
        FROM auditorium a
        LEFT JOIN (SELECT chain, cinema_id, MAX(cinema_name) cinema_name FROM current_showtime GROUP BY chain, cinema_id) c
               ON c.chain = a.chain AND c.cinema_id = a.cinema_id
        WHERE a.chain = ? GROUP BY a.cinema_id ORDER BY seats DESC""", (chain,))


def offered_seats(conn, d0=None, d1=None, from_now=True, hours=None):
    """Butacas ofertadas en la ventana = funciones × aforo de su sala, por cadena, y qué parte de las
    funciones tiene aforo conocido. Solo suma las funciones con sala conocida."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    return rows(conn, f"""
        SELECT s.chain, COUNT(*) shows, SUM(a.seats IS NOT NULL) shows_with_capacity,
               ROUND(100.0 * SUM(a.seats IS NOT NULL) / COUNT(*), 1) pct_known,
               SUM(a.seats) seats_offered, ROUND(AVG(a.seats)) avg_seats_per_show,
               COUNT(DISTINCT s.date) days, COUNT(DISTINCT s.cinema_id) cinemas
        FROM current_showtime s
        LEFT JOIN auditorium a ON a.chain = s.chain AND a.cinema_id = s.cinema_id AND a.screen = s.screen
        WHERE {where} GROUP BY s.chain ORDER BY s.chain""", params)


def offered_by_title(conn, d0=None, d1=None, from_now=True, limit=15, chain="cinepolis", hours=None):
    """Share de butacas ofertadas por título frente a share de funciones (solo cadenas con aforo)."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
    return rows(conn, f"""
        WITH base AS (
          SELECT s.title_norm, s.movie_title, a.seats
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


def occupancy_summary(conn, chain="cinepolis", phase="post"):
    """Muestras de ocupación acumuladas por color del semáforo: cuántas, % vendido medio, mínimo y máximo.
    `phase`: post (asistencia final, por defecto), pre (preventa a T−60) o all."""
    return rows(conn, f"""
        SELECT COALESCE(NULLIF(availability, ''), '(sin color)') availability, COUNT(*) samples,
               ROUND(AVG(sold_pct), 1) avg_sold_pct, MIN(sold_pct) min_sold_pct, MAX(sold_pct) max_sold_pct,
               SUM(sold) sold, SUM(seats) seats
        FROM occupancy_sample WHERE chain = ? AND {_PHASE[phase]} GROUP BY 1 ORDER BY avg_sold_pct DESC""", (chain,))


def occupancy_recent(conn, limit=50, chain="cinepolis", phase="post"):
    """Últimas muestras de ocupación de la cadena, con cine, función y % vendido."""
    return rows(conn, f"""
        SELECT o.sampled_at, COALESCE(c.cinema_name, o.cinema_id) cinema_name, o.screen, o.movie_title, o.datetime_local,
               o.minutes_to_start, o.seats, o.sold, o.sold_pct, o.availability
        FROM occupancy_sample o
        LEFT JOIN (SELECT chain, cinema_id, MAX(cinema_name) cinema_name FROM current_showtime GROUP BY chain, cinema_id) c
               ON c.chain = o.chain AND c.cinema_id = o.cinema_id
        WHERE o.chain = ? AND {_PHASE[phase]} ORDER BY o.id DESC LIMIT ?""", (chain, limit))


def prices(conn, days=14):
    """Precio de boleto general (mediana, mínimo y máximo) por cadena, cubeta de formato y tipo de día,
    sobre las muestras de los últimos `days` días."""
    return rows(conn, """
        WITH p AS (SELECT chain, format_bucket, day_type, general_cents, cinema_id
                   FROM price_sample WHERE general_cents IS NOT NULL
                     AND sampled_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ? || ' days')),
             ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY chain, format_bucket, day_type ORDER BY general_cents) rk,
                               COUNT(*) OVER (PARTITION BY chain, format_bucket, day_type) n FROM p)
        SELECT chain, format_bucket, day_type, MAX(n) samples, COUNT(DISTINCT cinema_id) cinemas,
               ROUND(AVG(CASE WHEN rk IN ((n + 1) / 2, (n + 2) / 2) THEN general_cents END) / 100.0, 0) median_price,
               MIN(general_cents) / 100.0 min_price, MAX(general_cents) / 100.0 max_price
        FROM ranked GROUP BY chain, format_bucket, day_type ORDER BY chain, format_bucket, day_type""", (f"-{int(days)}",))


def semaphore_calibration(conn, chain="cinemex", min_samples=5):
    """Qué % vendido corresponde a cada nivel del semáforo de una cadena, según las muestras de plano.
    Sirve para convertir el `availability` gratuito de cada snapshot en ocupación estimada."""
    return rows(conn, """
        SELECT COALESCE(NULLIF(availability, ''), '(sin color)') level, COUNT(*) samples,
               ROUND(100.0 * SUM(sold) / SUM(seats), 1) sold_pct,
               ROUND(AVG(sold_pct), 1) avg_sold_pct, MIN(sold_pct) min_sold_pct, MAX(sold_pct) max_sold_pct
        FROM occupancy_sample WHERE chain = ? AND seats > 0
        GROUP BY 1 HAVING COUNT(*) >= ? ORDER BY sold_pct DESC""", (chain, min_samples))


def estimated_occupancy(conn, d0=None, d1=None, from_now=True, chain="cinemex", min_samples=5, hours=None):
    """Butacas ocupadas estimadas en la ventana: aforo de la sala × % vendido calibrado del nivel de
    semáforo de cada función. Solo funciones con aforo conocido y nivel calibrado."""
    where, params, _ = _window(d0, d1, from_now, hours=hours)
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
