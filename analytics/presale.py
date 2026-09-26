"""Preventas de ambas cadenas: cuánto lleva vendido cada título en preventa y a qué ritmo (tabla `presale_sample`).

Cada título tiene, por cadena, un panel de funciones que `scraper/presale.py` relee a diario con el plano. La lectura
vigente de una función es la más reciente; el ritmo sale de dos lecturas de la misma función separadas entre 12 y 48 h,
para que una función que entra al panel no parezca haber vendido de golpe todo lo que ya llevaba. Todo va en % del
aforo del panel, comparable entre cadenas aunque tengan salas de distinto tamaño. `plaza` acota a los cines de esa
plaza; el panel solo existe en las plazas de `AC_SEATS_PLAZAS`.
"""
from datetime import date, datetime, timedelta, timezone

from .db import rows
from .plaza import plaza_cinema_where, plaza_where

# Una función está en el panel vigente si se leyó en los últimos dos días (el pase es diario).
_CURRENT_DAYS = 2
_PACE_MIN_H, _PACE_MAX_H = 12, 48


def presale_ranking(conn, chain="cinemex", plaza=None):
    """Por título en preventa: `title_norm`, `title`, `release_date`, `days_to_release`, `shows` (funciones del panel
    vigente), `seats`, `sold`, `sold_pct` (% del aforo del panel vendido), `sold_per_show`, `paced_shows` (funciones con
    dos lecturas comparables), `pace_per_show_day` (butacas por función y día), `pace_pct_day` (puntos de aforo vendidos
    por día sobre esas funciones; None sin dos lecturas) y `last_sampled`. Todo en % del aforo para que una sala IMAX
    no pese más que una tradicional. Orden: ritmo descendente (sin ritmo al final), luego % vendido y título."""
    where, params = plaza_cinema_where(plaza, chains=(chain,))
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=_CURRENT_DAYS)).isoformat(timespec="seconds")
    readings = rows(conn, f"""
        SELECT show_id, title_key(title_norm) title_norm, movie_title, release_date, sampled_at, seats, sold
        FROM presale_sample WHERE chain = ? AND seats > 0{where}
        ORDER BY show_id, sampled_at""", (chain, *params))
    by_show = {}
    for r in readings:
        by_show.setdefault(r["show_id"], []).append(r)
    titles = {}
    for show in by_show.values():
        last = show[-1]
        if last["sampled_at"] < since:
            continue
        t = titles.setdefault(last["title_norm"], {"title": last["movie_title"].strip(), "release_date": last["release_date"],
                                                    "shows": 0, "seats": 0, "sold": 0, "paced_shows": 0, "paced_seats": 0, "pace_sold": 0.0,
                                                    "last_sampled": ""})
        t["shows"] += 1
        t["seats"] += last["seats"]
        t["sold"] += last["sold"]
        t["last_sampled"] = max(t["last_sampled"], last["sampled_at"])
        t_last = datetime.fromisoformat(last["sampled_at"])
        prev = next((p for p in reversed(show[:-1])
                     if _PACE_MIN_H <= (t_last - datetime.fromisoformat(p["sampled_at"])).total_seconds() / 3600 <= _PACE_MAX_H), None)
        if prev:
            hours = (t_last - datetime.fromisoformat(prev["sampled_at"])).total_seconds() / 3600
            t["paced_shows"] += 1
            t["paced_seats"] += last["seats"]
            t["pace_sold"] += (last["sold"] - prev["sold"]) * 24 / hours
    today = date.today()
    out = []
    for title_norm, t in titles.items():
        release = t["release_date"]
        out.append({"title_norm": title_norm, "title": t["title"], "release_date": release,
                    "days_to_release": (date.fromisoformat(release) - today).days if release else None,
                    "shows": t["shows"], "seats": t["seats"], "sold": t["sold"],
                    "sold_pct": round(100.0 * t["sold"] / t["seats"], 1) if t["seats"] else 0.0,
                    "sold_per_show": round(t["sold"] / t["shows"], 1),
                    "paced_shows": t["paced_shows"],
                    "pace_per_show_day": round(t["pace_sold"] / t["paced_shows"], 2) if t["paced_shows"] else None,
                    "pace_pct_day": round(100.0 * t["pace_sold"] / t["paced_seats"], 2) if t["paced_seats"] else None,
                    "last_sampled": t["last_sampled"]})
    return sorted(out, key=lambda r: (r["pace_pct_day"] is None, -(r["pace_pct_day"] or 0), -r["sold_pct"], r["title_norm"]))


def presale_curve(conn, title_norm, chain="cinemex", plaza=None):
    """Curva de venta de un título (`title_norm` es la llave de `presale_ranking`): por días al inicio de la función (entero, hacia abajo), `readings`, `seats`, `sold` y
    `sold_pct` de todas las lecturas del panel. Orden: más días al inicio primero, como se lee una preventa."""
    where, params = plaza_cinema_where(plaza, chains=(chain,))
    return rows(conn, f"""
        SELECT CAST(days_to_start AS INTEGER) days_to_start, COUNT(*) readings, SUM(seats) seats, SUM(sold) sold,
               ROUND(100.0 * SUM(sold) / SUM(seats), 1) sold_pct
        FROM presale_sample WHERE chain = ? AND title_key(title_norm) = ? AND seats > 0 AND days_to_start >= 0{where}
        GROUP BY 1 ORDER BY 1 DESC""", (chain, title_norm, *params))


def presale_compare(conn, plaza=None):
    """Una fila por título en preventa en alguna de las dos cadenas, emparejadas por la llave de título común
    (`scraper/titles.py`): `title`,
    `title_norm_cinemex`, `title_norm_cinepolis`, y por cadena `shows_*`, `sold_pct_*` y `pace_pct_day_*` (None si esa
    cadena no lo tiene en preventa o no tiene ritmo), `sold_*` y `seats_*` (butacas vendidas y aforo del panel), `gap_pp` (Cinemex − Cinépolis en % vendido; None si falta una) y
    `release_date` y `status`: `ambas` (en preventa en las dos), `exclusiva_cinemex` / `exclusiva_cinepolis` (la otra
    cadena no lo tiene en su cartelera de la plaza) o `solo_cinemex` / `solo_cinepolis` (la otra lo exhibe, pero fuera de
    su lista de preventa). Orden: mayor % vendido en cualquiera de las dos, luego título."""
    ours = presale_ranking(conn, chain="cinemex", plaza=plaza)
    theirs = presale_ranking(conn, chain="cinepolis", plaza=plaza)
    where, params = plaza_where(plaza)
    exhibited = {c: {r["k"] for r in rows(conn, f"""
        SELECT DISTINCT title_key(title_norm) k FROM current_showtime WHERE chain = ?{where}""", (c, *params))}
                 for c in ("cinemex", "cinepolis")}

    def status(u, t):
        if u and t:
            return "ambas"
        own, other = ("cinemex", "cinepolis") if u else ("cinepolis", "cinemex")
        norm = (u or t)["title_norm"]
        return f"solo_{own}" if norm in exhibited[other] else f"exclusiva_{own}"
    pairs, used = [], set()
    for u in ours:
        t = next((x for x in theirs if x["title_norm"] == u["title_norm"]), None)
        if t:
            used.add(t["title_norm"])
        pairs.append((u, t))
    pairs += [(None, t) for t in theirs if t["title_norm"] not in used]
    out = []
    for u, t in pairs:
        base = u or t
        out.append({"title": base["title"], "release_date": base["release_date"] or (t or {}).get("release_date"),
                    "title_norm_cinemex": u and u["title_norm"], "title_norm_cinepolis": t and t["title_norm"],
                    "shows_cinemex": u["shows"] if u else 0, "shows_cinepolis": t["shows"] if t else 0,
                    "sold_cinemex": u["sold"] if u else 0, "sold_cinepolis": t["sold"] if t else 0,
                    "seats_cinemex": u["seats"] if u else 0, "seats_cinepolis": t["seats"] if t else 0,
                    "sold_pct_cinemex": u and u["sold_pct"], "sold_pct_cinepolis": t and t["sold_pct"],
                    "pace_pct_day_cinemex": u and u["pace_pct_day"], "pace_pct_day_cinepolis": t and t["pace_pct_day"],
                    "gap_pp": round(u["sold_pct"] - t["sold_pct"], 1) if u and t else None, "status": status(u, t)})
    return sorted(out, key=lambda r: (-max(r["sold_pct_cinemex"] or 0, r["sold_pct_cinepolis"] or 0), r["title"]))
