"""Preventas de ambas cadenas: qué títulos están en preventa y cuántas butacas lleva vendidas cada uno.

Uso:
  python3 -m scraper.presale [--chain cinemex|cinepolis] [--dry-run] [--limit N] [--per-title 30]

Fuentes (verificado 2026-09-25, ver project.md > "Preventas"). Un título está en preventa hasta el día de su estreno y
cuentan todas sus funciones (en un evento de una noche la única fecha es el estreno); sin estreno conocido, mientras
siga en la lista de su cadena.
  - Cinemex. Títulos: la landing `preventas` de `GET landings/` (cinemex.com/landing/preventas/peliculas/). Estreno:
    `upcoming.movies[]{movie_id, name, release_date}`, incrustado en el HTML del sitio. Funciones: `current_showtime`
    para los `CINEMEX_DAYS_AHEAD` días capturados y la cartelera por estado para las fechas que publica después.
    Butacas: el plano público de `GET sessions/{id}`.
  - Cinépolis. Títulos y estreno: `movies(category: "coming-soon")` (cinepolis.com/mx/proximamente). Funciones: ya
    están en `current_showtime`, porque su cartelera trae todas las fechas publicadas. Butacas: `query Seats`. Un plano
    que responde "esta función ya no está disponible (101)" antes de empezar se cuenta aparte, no como falla: en la
    primera prueba coincidió con funciones de poca disponibilidad.
  Solo los cines de `config.SEATS_PLAZAS`.

Panel: por título, las funciones ya muestreadas que aún no empiezan más funciones nuevas hasta `PRESALE_PANEL_PER_TITLE`,
repartidas entre cines. Cada función del panel se relee a diario: dos lecturas de la misma función dan su ritmo de
venta. Escribe `presale_sample` y el crudo de la corrida en `data/raw/{chain}_presale/`.
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone

from . import cinemex, cinepolis, config, normalize, plazas, sample, store
from .http import ApiError, AuthError, Blocked, RateLimited, request_text

log = sample.log


def presale_titles(landings):
    """[{movie_id, title}] de la landing de preventas; vacío si Cinemex la quitó o la dejó sin películas."""
    for landing in landings or []:
        if landing.get("slug") != config.PRESALE_LANDING_SLUG:
            continue
        for page in landing.get("pages") or []:
            if page.get("type") == "showtimes":
                movies = (page.get("content") or {}).get("movies") or []
                return [{"movie_id": str(m["id"]), "title": (m.get("name") or "").strip()} for m in movies if m.get("id")]
    return []


def release_dates(html):
    """{movie_id: fecha} y {title_norm: fecha} del bloque `var upcoming={…}` del HTML del sitio. El `movie_id` viene
    vacío en muchos títulos, por eso también se indexa por título normalizado."""
    start = html.find("var upcoming=")
    if start < 0:
        return {}, {}
    upcoming, _ = json.JSONDecoder().raw_decode(html, start + len("var upcoming="))
    by_id, by_title = {}, {}
    for m in upcoming.get("movies") or []:
        released = m.get("release_date")
        if not released:
            continue
        if m.get("movie_id"):
            by_id[str(m["movie_id"])] = released
        by_title[normalize.norm_title(m.get("name"))] = released
    return by_id, by_title


def in_presale(release_date, today):
    """Un título sigue en preventa hasta su estreno; sin estreno conocido, mientras esté en la landing."""
    return release_date is None or today < release_date


def pick_panel(candidates, sampled, per_title):
    """Funciones a leer hoy, por título: las que ya están en el panel (`sampled`, show_ids) y siguen vigentes, más nuevas
    hasta `per_title`, una por cine en cada vuelta (la más próxima de cada cine primero). Determinista."""
    by_title = {}
    for r in candidates:
        by_title.setdefault(r["movie_id"], []).append(r)
    picked = []
    for movie_id in sorted(by_title):
        rows = sorted(by_title[movie_id], key=lambda r: (r["datetime_utc"] or "", r["cinema_id"], r["show_id"]))
        keep = [r for r in rows if r["show_id"] in sampled][:per_title]
        by_cinema = {}
        for r in rows:
            if r["show_id"] not in sampled:
                by_cinema.setdefault(r["cinema_id"], []).append(r)
        new = []
        while len(keep) + len(new) < per_title and any(by_cinema.values()):
            for cinema_id in sorted(by_cinema):
                if by_cinema[cinema_id] and len(keep) + len(new) < per_title:
                    new.append(by_cinema[cinema_id].pop(0))
        picked.extend(keep + new)
    return picked


def _plaza_states(conn, scope):
    keys = plazas.city_ids_for(scope, "cinemex")
    if not keys:
        return []
    marks = ",".join("?" for _ in keys)
    return sorted({r[0] for r in conn.execute(
        f"SELECT DISTINCT state_id FROM cinema WHERE chain = 'cinemex' AND city_id IN ({marks}) AND state_id IS NOT NULL", keys)})


def _cinemex_sources(conn, scope, taken_at, stats):
    """Títulos de la landing con su estreno, y las funciones de las fechas que la captura no pide. Devuelve
    (titles, extra_rows, raw)."""
    landing = presale_titles(cinemex.get("landings/", stats=stats))
    by_id, by_title = release_dates(request_text(config.CINEMEX_SITE_URL))
    titles = [dict(t, release_date=by_id.get(t["movie_id"]) or by_title.get(normalize.norm_title(t["title"]))) for t in landing]
    horizon = (date.fromisoformat(taken_at[:10]) + timedelta(days=config.CINEMEX_DAYS_AHEAD)).isoformat()
    far = [cinemex.state_days_after(state_id, horizon, stats) for state_id in _plaza_states(conn, scope)] if titles else []
    raw = {"chain": "cinemex", "taken_at": taken_at, "titles": titles, "states": far}
    return titles, normalize.rows("cinemex", raw) if far else [], raw


def _cinepolis_sources(conn, scope, taken_at, stats):
    """Títulos de "Próximamente" con su estreno; sus funciones ya están en la captura."""
    titles = [{"movie_id": m["id"], "title": (m.get("name") or "").strip(), "release_date": (m.get("releaseDate") or "")[:10] or None}
              for m in cinepolis.coming_soon(stats) if m.get("id")]
    return titles, [], {"chain": "cinepolis", "taken_at": taken_at, "titles": titles}


_SOURCES = {"cinemex": _cinemex_sources, "cinepolis": _cinepolis_sources}


def candidates(conn, chain, titles, extra_rows, scope):
    """Funciones de preventa aún no iniciadas de los títulos, en los cines de `scope`: la cartelera capturada más
    `extra_rows` (fechas lejanas de Cinemex). Cada fila lleva el `release_date` de su título."""
    release = {t["movie_id"]: t["release_date"] for t in titles}
    city_ids = set(plazas.city_ids_for(scope, chain))
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    marks = ",".join("?" for _ in release)
    near = [dict(r) for r in conn.execute(f"""
        SELECT show_id, cinema_id, screen, movie_id, movie_title, title_norm, date, datetime_local, datetime_utc, city_id
        FROM current_showtime WHERE chain = ? AND movie_id IN ({marks}) AND datetime_utc > ?""", (chain, *release, now_utc))] if release else []
    today = sample.now_local().date().isoformat()
    rows, seen = [], set()
    for r in near + [r for r in extra_rows if r["movie_id"] in release]:
        if r["show_id"] in seen or r["city_id"] not in city_ids or (r["datetime_utc"] or "") <= now_utc:
            continue
        if in_presale(release[r["movie_id"]], today):
            seen.add(r["show_id"])
            rows.append(dict(r, chain=chain, release_date=release[r["movie_id"]]))
    return rows


def _unavailable(error):
    """Cinépolis responde (101) "esta función ya no está disponible" en funciones que siguen publicadas."""
    return "(101)" in str(error)


def presale_pass(conn, chain="cinemex", per_title=config.PRESALE_PANEL_PER_TITLE, limit=None, dry_run=False,
                 scope=config.SEATS_PLAZAS):
    stats = {"calls": 0}
    taken_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    titles, extra_rows, raw = _SOURCES[chain](conn, scope, taken_at, stats)
    if not titles:
        log(f"presale {chain}: la lista de preventa no trae películas")
        return False
    rows = candidates(conn, chain, titles, extra_rows, scope)
    sampled = {r[0] for r in conn.execute("SELECT DISTINCT show_id FROM presale_sample WHERE chain = ? AND datetime_utc > ?",
                                          (chain, taken_at))}
    panel = pick_panel(rows, sampled, per_title)
    if limit:
        panel = panel[:limit]
    per_movie = {}
    for r in rows:
        per_movie[r["movie_id"]] = per_movie.get(r["movie_id"], 0) + 1
    log(f"presale {chain} [{','.join(scope)}]: {len(titles)} títulos en la lista, {len(per_movie)} con funciones de preventa, "
        f"{len(rows)} funciones ({len(extra_rows)} de fechas lejanas), panel de {len(panel)} "
        f"({len([r for r in panel if r['show_id'] in sampled])} ya muestreadas){' (dry-run)' if dry_run else ''}")
    for t in titles:
        if per_movie.get(t["movie_id"]):
            log(f"  {t['movie_id']} {t['title'][:40]}: estreno {t['release_date'] or '—'}, {per_movie[t['movie_id']]} funciones en la plaza")
    if dry_run:
        return True
    store.save_raw(f"{chain}_presale", taken_at, raw)
    vids = sample.vista_ids(conn) if chain == "cinepolis" else {}
    ok = fail = unavailable = 0
    for r in panel:
        try:
            lay = sample.layout_for(chain, r, vids, stats)
        except (AuthError, Blocked, RateLimited):
            raise
        except ApiError as e:
            if _unavailable(e):
                unavailable += 1
            else:
                fail += 1; log(f"presale FAIL {chain} {r['show_id']}: {e}"[:300])
            time.sleep(config.SAMPLE_BACKOFF); continue
        time.sleep(config.SAMPLE_PAUSE)
        if not lay:
            fail += 1; continue
        now = datetime.now(timezone.utc)
        days = (datetime.fromisoformat(r["datetime_utc"]) - now).total_seconds() / 86400
        conn.execute("""INSERT INTO presale_sample (chain, show_id, movie_id, movie_title, title_norm, cinema_id, screen, date,
                            datetime_local, datetime_utc, release_date, sampled_at, days_to_start, seats, sold)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (chain, r["show_id"], r["movie_id"], r["movie_title"], r["title_norm"], r["cinema_id"], r["screen"], r["date"],
                      r["datetime_local"], r["datetime_utc"], r["release_date"], now.isoformat(timespec="seconds"),
                      round(days, 2), lay["seats"], lay["sold"]))
        conn.commit(); ok += 1
    log(f"presale {chain} ok={ok} no_disponibles={unavailable} fail={fail} calls={stats['calls']}")
    return fail == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chain", choices=["cinemex", "cinepolis"], default="cinemex")
    ap.add_argument("--per-title", type=int, default=config.PRESALE_PANEL_PER_TITLE, help="funciones del panel por título")
    ap.add_argument("--limit", type=int, help="tope de planos en esta corrida")
    ap.add_argument("--dry-run", action="store_true", help="lista títulos, estrenos y panel sin leer planos")
    a = ap.parse_args(argv)
    conn = store.connect()
    t0 = time.time()
    ok = presale_pass(conn, chain=a.chain, per_title=a.per_title, limit=a.limit, dry_run=a.dry_run)
    conn.close()
    log(f"done in {time.time() - t0:.0f}s ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
