"""Mapa de cines: una fila por complejo con sus coordenadas y lo que sabemos de él (funciones, salas, butacas, boleto,
palomitas, ocupación), y los destacados de cada cadena.

Cada dato es el más reciente que existe para ese cine y lleva su fecha, porque los muestreos se renuevan a ritmos
distintos (precios cada semana, dulcería cada semana, planos cada hora). Un cine sin un dato lo devuelve en None: el
mapa no rellena. El boleto se compara en una sola combinación para que dos cines sean comparables: formato tradicional,
viernes a domingo. Las palomitas en sala solo existen por complejo en Cinépolis (Cinemex tiene una lista única).
"""
from .concessions import concession_product_by_cinema
from .db import rows
from .labels import CHAIN_LABEL, CINEMA_TYPE_LABEL
from .plaza import plaza_cinema_where, plaza_where
from .queries import _window

MAP_CHAINS = tuple(CHAIN_LABEL)                 # el mapa muestra las tres; los destacados comparan dentro de cada cadena
TICKET_FORMAT, TICKET_DAY_TYPE = "traditional", "weekend"
POPCORN = "Palomitas"
OCCUPANCY_DAYS = 7
OCCUPANCY_MIN_SAMPLES = 10       # planos de un cine en la ventana para afirmar su ocupación
# Eventos y matinés tienen precio propio (un "Evento Matinée" a $15 el 2026-09-08); el muestreo ya los salta, pero las
# lecturas anteriores siguen en la base.
_NOT_EVENT = "lower(COALESCE(tickets_json, '')) NOT LIKE '%matin%' AND lower(COALESCE(tickets_json, '')) NOT LIKE '%evento%'"
# El complejo y su sala Platino o VIP comparten coordenadas exactas: a menos de ~10 m son el mismo edificio.
_SITE_DECIMALS = 4
# Métrica → sentido del destacado: "min" gana el más bajo (precio), "max" el más alto.
HIGHLIGHTS = {"ticket_price": "min", "ticket_max": "max", "popcorn_price": "min", "shows": "max", "screens": "max", "seats": "max", "sold_pct": "max"}


def cinema_map(conn, d0=None, d1=None, from_now=True, plaza=None, chains=MAP_CHAINS, cinema_ids=None):
    """Por cine con coordenadas: `chain`, `cinema_id`, `cinema_name`, `lat`, `lng`, `shows` y `titles` (en la ventana),
    `screens` y `seats` (aforo medido), `ticket_price` y `ticket_sampled_at` (boleto general tradicional de viernes a
    domingo, la lectura más reciente sin eventos ni matinés), `ticket_max`, `ticket_max_format` y
    `ticket_max_sampled_at` (el boleto general más caro en cualquier formato y día, entre la lectura más reciente de
    cada combinación), `popcorn_price` (palomitas en sala), `sold_pct` y
    `occupancy_samples` (planos tras el inicio de los últimos 7 días, con al menos 10). None donde no hay dato.
    `cinema_ids` deja solo esos cines (None = todos los de la zona). El nombre lleva "VIP" cuando la cadena usa el mismo
    para el complejo y su sala VIP. Orden: cadena y nombre."""
    where, params = plaza_where(plaza, chains=chains)
    cinemas = rows(conn, f"""
        SELECT chain, cinema_id, name cinema_name, lat, lng FROM cinema
        WHERE lat IS NOT NULL AND lng IS NOT NULL{where} ORDER BY chain, name, cinema_id""", params)
    if cinema_ids is not None:
        cinemas = [r for r in cinemas if r["cinema_id"] in set(cinema_ids)]
    key = lambda r: (r["chain"], r["cinema_id"])  # noqa: E731

    w, p, _ = _window(d0, d1, from_now, plaza=plaza, chains=chains)
    shows = {key(r): r for r in rows(conn, f"""
        SELECT chain, cinema_id, COUNT(*) shows, COUNT(DISTINCT title_key(title_norm)) titles
        FROM current_showtime WHERE {w} GROUP BY chain, cinema_id ORDER BY chain, cinema_id""", p)}
    cw, cp = plaza_cinema_where(plaza, chains=chains)
    capacity = {key(r): r for r in rows(conn, f"""
        SELECT chain, cinema_id, COUNT(*) screens, SUM(seats) seats FROM auditorium
        WHERE 1 = 1{cw} GROUP BY chain, cinema_id ORDER BY chain, cinema_id""", cp)}
    tickets = {key(r): r for r in rows(conn, f"""
        WITH ranked AS (SELECT chain, cinema_id, general_cents, sampled_at,
                               ROW_NUMBER() OVER (PARTITION BY chain, cinema_id ORDER BY sampled_at DESC, id DESC) rk
                        FROM price_sample
                        WHERE general_cents > 0 AND format_bucket = ? AND day_type = ? AND {_NOT_EVENT}{cw})
        SELECT chain, cinema_id, general_cents / 100.0 ticket_price, sampled_at ticket_sampled_at
        FROM ranked WHERE rk = 1 ORDER BY chain, cinema_id""", (TICKET_FORMAT, TICKET_DAY_TYPE, *cp))}
    # El boleto más caro: el general más alto entre la lectura más reciente de cada formato y tipo de día.
    top_tickets = {key(r): r for r in rows(conn, f"""
        WITH ranked AS (SELECT chain, cinema_id, format_bucket, general_cents, sampled_at,
                               ROW_NUMBER() OVER (PARTITION BY chain, cinema_id, format_bucket, day_type
                                                  ORDER BY sampled_at DESC, id DESC) rk
                        FROM price_sample WHERE general_cents > 0 AND {_NOT_EVENT}{cw}),
             top AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY chain, cinema_id ORDER BY general_cents DESC, format_bucket) pick
                     FROM ranked WHERE rk = 1)
        SELECT chain, cinema_id, general_cents / 100.0 ticket_max, format_bucket ticket_max_format, sampled_at ticket_max_sampled_at
        FROM top WHERE pick = 1 ORDER BY chain, cinema_id""", cp)}
    popcorn = {("cinepolis", r["cinema_id"]): r["price"]
               for r in concession_product_by_cinema(conn, POPCORN, plaza=plaza)} if "cinepolis" in chains else {}
    occupancy = {key(r): r for r in rows(conn, f"""
        SELECT chain, cinema_id, COUNT(*) occupancy_samples, ROUND(100.0 * SUM(sold) / SUM(seats), 1) sold_pct
        FROM occupancy_sample
        WHERE minutes_to_start < 0 AND seats > 0 AND sold IS NOT NULL
          AND sampled_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?){cw}
        GROUP BY chain, cinema_id HAVING COUNT(*) >= ? ORDER BY chain, cinema_id""",
                                         (f"-{OCCUPANCY_DAYS} days", *cp, OCCUPANCY_MIN_SAMPLES))}

    for r in cinemas:
        k = key(r)
        # Cinépolis llama igual al complejo y a su VIP ("Plaza Carso"); solo el id lo distingue.
        if "vip" in r["cinema_id"] and "vip" not in (r["cinema_name"] or "").lower():
            r["cinema_name"] = f"{r['cinema_name']} {CINEMA_TYPE_LABEL['vip']}"
        s, c, t, o, x = shows.get(k, {}), capacity.get(k, {}), tickets.get(k, {}), occupancy.get(k, {}), top_tickets.get(k, {})
        r.update(shows=s.get("shows", 0), titles=s.get("titles", 0), screens=c.get("screens"), seats=c.get("seats"),
                 ticket_price=t.get("ticket_price"), ticket_sampled_at=t.get("ticket_sampled_at"),
                 ticket_max=x.get("ticket_max"), ticket_max_format=x.get("ticket_max_format"),
                 ticket_max_sampled_at=x.get("ticket_max_sampled_at"),
                 popcorn_price=popcorn.get(k), sold_pct=o.get("sold_pct"), occupancy_samples=o.get("occupancy_samples", 0))
    return cinemas


def cinema_highlights(conn, d0=None, d1=None, from_now=True, plaza=None, chains=MAP_CHAINS, cinema_ids=None):
    """El cine destacado de cada cadena en cada métrica de `HIGHLIGHTS`: `metric`, `chain`, `cinema_id`, `cinema_name`,
    `value` y `cinemas` (cuántos cines de la cadena tienen el dato), sobre los mismos cines que `cinema_map`. Una métrica sin dato en una cadena no aparece; un
    empate lo gana el nombre alfabético. Orden: métrica en el orden de `HIGHLIGHTS`, luego cadena."""
    data = cinema_map(conn, d0, d1, from_now, plaza=plaza, chains=chains, cinema_ids=cinema_ids)
    out = []
    for metric, sense in HIGHLIGHTS.items():
        for chain in chains:
            have = [r for r in data if r["chain"] == chain and r[metric]]
            if not have:
                continue
            sign = 1 if sense == "min" else -1
            best = min(have, key=lambda r: (sign * r[metric], r["cinema_name"] or "", r["cinema_id"]))
            out.append({"metric": metric, "chain": chain, "cinema_id": best["cinema_id"], "cinema_name": best["cinema_name"],
                        "value": best[metric], "cinemas": len(have)})
    return out


def cinema_sites(conn, d0=None, d1=None, from_now=True, plaza=None, chains=MAP_CHAINS, cinema_ids=None):
    """Los cines de `cinema_map` agrupados por lugar: una fila por cadena y coordenadas (redondeadas a ~10 m), porque
    un complejo y su sala Platino o VIP comparten edificio. Por fila: `site_id`, `chain`, `lat`, `lng` y `cinemas` (las
    filas de `cinema_map` de ese lugar, por nombre). Orden: cadena y primer nombre."""
    sites = {}
    for r in cinema_map(conn, d0, d1, from_now, plaza=plaza, chains=chains, cinema_ids=cinema_ids):
        key = f"{r['chain']}:{round(r['lat'], _SITE_DECIMALS)},{round(r['lng'], _SITE_DECIMALS)}"
        sites.setdefault(key, {"site_id": key, "chain": r["chain"], "lat": r["lat"], "lng": r["lng"], "cinemas": []})["cinemas"].append(r)
    for s in sites.values():
        s["cinemas"].sort(key=lambda r: (r["cinema_name"] or "", r["cinema_id"]))
    return sorted(sites.values(), key=lambda s: (s["chain"], s["cinemas"][0]["cinema_name"] or "", s["site_id"]))
