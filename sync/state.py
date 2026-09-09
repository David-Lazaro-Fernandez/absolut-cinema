"""Motor de historia de funciones: identidad (`showtime`) + versiones de estado (`showtime_state`).

Cada captura buena se procesa en orden a partir de su crudo (`snapshot.raw_path`), normalizado con el mismo
`scraper.normalize.rows` que usa el scraper. `plan()` es puro: compara las filas de la captura con el estado abierto
en memoria y decide altas, cierres, versiones nuevas y correcciones de identidad con las mismas reglas que el diff
del scraper (`scraper.diff.closing_kind`, `scraper.diff.changed_fields`). `apply()` escribe el plan en una sola
transacción y actualiza el estado en memoria, así una corrida procesa muchas capturas con una sola lectura inicial.
"""
import gzip
import json
from datetime import timedelta

from scraper import config, normalize
from scraper.diff import changed_fields, closing_kind
from scraper.normalize import CHANGE_FIELDS, MOVE_FIELDS, TRACKED_FIELDS

from . import pg

# Campos de la versión de estado, en el orden de la tabla showtime_state (sin las llaves ni la vigencia).
STATE_FIELDS = ("datetime_local", "screen", "language", "language_raw", "format", "experience", "premium_tier",
                "version_raw", "availability")
IDENTITY_FIELDS = ("cinema_id", "movie_id")
# Lo que abre una versión nueva: todo lo rastreado menos la identidad, que se corrige en `showtime`.
VERSION_FIELDS = tuple(f for f in TRACKED_FIELDS if f not in IDENTITY_FIELDS)


def load_open(cur, chain):
    """Estado abierto de una cadena: {(show_id, show_date): fila con identidad + campos de la versión vigente},
    con los nombres de campo del normalizador para poder comparar con `changed_fields`."""
    cur.execute("""
        SELECT s.show_id, s.show_date, s.cinema_id, s.movie_id,
               st.starts_at, st.screen, st.language, st.language_raw, st.format, st.experience, st.premium_tier,
               st.version_raw, st.availability
        FROM showtime s JOIN showtime_state st
          ON st.chain = s.chain AND st.show_id = s.show_id AND st.show_date = s.show_date AND st.valid_to IS NULL
        WHERE s.chain = %s::chain_t AND s.closed_at IS NULL""", (chain,))
    out = {}
    for r in cur.fetchall():
        show_id, show_date = r[0], r[1]
        out[(show_id, show_date.isoformat())] = {
            "show_id": show_id, "date": show_date.isoformat(), "cinema_id": r[2], "movie_id": r[3],
            "datetime_local": r[4].strftime("%Y-%m-%dT%H:%M:%S") if r[4] else None, "screen": r[5], "language": r[6],
            "language_raw": r[7], "format": r[8], "experience": r[9], "premium_tier": r[10], "version_raw": r[11],
            "availability": r[12]}
    return out


def plan(chain, open_state, rows, taken_at):
    """Compara las filas normalizadas de una captura con el estado abierto y devuelve qué escribir. Puro."""
    seen = set()
    out = {"new": [], "close": [], "versions": [], "identity": [], "cinemas": {}, "movies": {}, "unchanged": 0}
    for row in rows:
        if not row.get("datetime_local") or not row.get("date"):
            continue
        key = (row["show_id"], row["date"])
        seen.add(key)
        out["cinemas"][row["cinema_id"]] = row
        out["movies"][row["movie_id"]] = row
        prev = open_state.get(key)
        if prev is None:
            out["new"].append(row)
            continue
        if changed_fields(prev, row, IDENTITY_FIELDS):
            out["identity"].append(row)
        if changed_fields(prev, row, VERSION_FIELDS):
            out["versions"].append(row)
        elif not changed_fields(prev, row, IDENTITY_FIELDS):
            out["unchanged"] += 1
    for key, prev in open_state.items():
        if key not in seen:
            out["close"].append((prev, closing_kind(prev.get("datetime_local"), taken_at)))
    return out


def cinema_cities(chain, raw):
    """{cinema_id: city_id} desde el crudo: Cinépolis trae la ciudad a nivel captura; Cinemex, el estado por cine."""
    if chain == "cinepolis":
        city = raw.get("city_id")
        return {str(c.get("id")): city for c in raw.get("cinemas", [])}
    out = {}
    for area in raw.get("areas", []):
        for day in area.get("days", []):
            for c in (day.get("data") or {}).get("cinemas") or []:
                state = (c.get("state") or {}).get("id")
                out[str(c.get("id"))] = str(state) if state is not None else None
    return out


def apply(cur, chain, planned, taken_at, cities):
    """Escribe el plan de una captura (una transacción a cargo del llamador) y devuelve conteos."""
    t = pg.to_ts(taken_at)
    dates = [pg.to_date(r["date"]) for r in planned["new"] + planned["versions"]]
    pg.ensure_partitions(cur, "showtime", dates)
    pg.ensure_partitions(cur, "showtime_state", dates)
    # Catálogo: cines y películas vistos en esta captura.
    cur.executemany("""
        INSERT INTO cinema (chain, cinema_id, name, lat, lng, city_id, first_seen, last_seen)
        VALUES (%s::chain_t, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chain, cinema_id) DO UPDATE SET name = EXCLUDED.name, lat = COALESCE(EXCLUDED.lat, cinema.lat),
            lng = COALESCE(EXCLUDED.lng, cinema.lng), city_id = COALESCE(EXCLUDED.city_id, cinema.city_id), last_seen = EXCLUDED.last_seen""",
        [(chain, cid, r.get("cinema_name") or cid, pg.to_float(r.get("lat")), pg.to_float(r.get("lng")), cities.get(str(cid)), t, t)
         for cid, r in planned["cinemas"].items()])
    cur.executemany("""
        INSERT INTO movie (chain, movie_id, title, title_norm, genre, rating, duration_min, distributor, first_seen, last_seen)
        VALUES (%s::chain_t, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chain, movie_id) DO UPDATE SET title = EXCLUDED.title, title_norm = EXCLUDED.title_norm,
            genre = COALESCE(EXCLUDED.genre, movie.genre), rating = COALESCE(EXCLUDED.rating, movie.rating),
            duration_min = COALESCE(EXCLUDED.duration_min, movie.duration_min),
            distributor = COALESCE(EXCLUDED.distributor, movie.distributor), last_seen = EXCLUDED.last_seen""",
        [(chain, mid, r.get("movie_title") or mid, r.get("title_norm") or (r.get("movie_title") or mid).lower(), r.get("genre") or None,
          r.get("rating") or None, pg.to_int(r.get("duration_min")), r.get("distributor") or None, t, t)
         for mid, r in planned["movies"].items()])
    # Cierres: la versión vigente termina y la función se cierra con su motivo.
    closing = [(prev, kind) for prev, kind in planned["close"]]
    cur.executemany("""UPDATE showtime_state SET valid_to = %s WHERE chain = %s::chain_t AND show_id = %s AND show_date = %s AND valid_to IS NULL""",
                    [(t, chain, prev["show_id"], prev["date"]) for prev, _ in closing])
    cur.executemany("""UPDATE showtime SET closed_at = %s, closed_kind = %s WHERE chain = %s::chain_t AND show_id = %s AND show_date = %s""",
                    [(t, kind, chain, prev["show_id"], prev["date"]) for prev, kind in closing])
    # Versiones nuevas de funciones ya abiertas: cerrar la vigente.
    cur.executemany("""UPDATE showtime_state SET valid_to = %s WHERE chain = %s::chain_t AND show_id = %s AND show_date = %s AND valid_to IS NULL""",
                    [(t, chain, r["show_id"], r["date"]) for r in planned["versions"]])
    # Corrección de identidad (película o cine): hoy no ocurre; el detalle queda en event.changes.
    cur.executemany("""UPDATE showtime SET cinema_id = %s, movie_id = %s WHERE chain = %s::chain_t AND show_id = %s AND show_date = %s""",
                    [(r["cinema_id"], r["movie_id"], chain, r["show_id"], r["date"]) for r in planned["identity"]])
    # Altas: una función nueva, o una cerrada que reaparece (misma llave): se reabre conservando first_seen_at.
    reopened = 0
    for r in planned["new"]:
        cur.execute("""
            INSERT INTO showtime (chain, show_id, show_date, cinema_id, movie_id, first_seen_at, closed_at, closed_kind)
            VALUES (%s::chain_t, %s, %s, %s, %s, %s, NULL, NULL)
            ON CONFLICT (chain, show_id, show_date) DO UPDATE SET closed_at = NULL, closed_kind = NULL,
                cinema_id = EXCLUDED.cinema_id, movie_id = EXCLUDED.movie_id
            RETURNING (first_seen_at < %s) AS reopened""", (chain, r["show_id"], pg.to_date(r["date"]), r["cinema_id"], r["movie_id"], t, t))
        # first_seen_at solo es anterior a esta captura si la fila ya existía: una función cerrada que reaparece.
        reopened += 1 if cur.fetchone()[0] else 0
    cur.executemany("""
        INSERT INTO showtime_state (chain, show_id, show_date, valid_from, valid_to, starts_at, screen, language, language_raw,
                                    format, experience, premium_tier, version_raw, availability)
        VALUES (%s::chain_t, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chain, show_id, show_date, valid_from) DO NOTHING""",
        [(chain, r["show_id"], pg.to_date(r["date"]), t, pg.to_local(r["datetime_local"]), r.get("screen") or None,
          r.get("language") or None, r.get("language_raw") or None, r.get("format") or None, r.get("experience") or None,
          r.get("premium_tier") or None, r.get("version_raw") or None, r.get("availability") or None)
         for r in planned["new"] + planned["versions"]])
    return {"new": len(planned["new"]) - reopened, "reopened": reopened, "closed": len(closing), "versions": len(planned["versions"]),
            "identity": len(planned["identity"]), "unchanged": planned["unchanged"]}


def refresh_open(open_state, planned):
    """Actualiza el estado en memoria tras aplicar el plan."""
    for prev, _ in planned["close"]:
        open_state.pop((prev["show_id"], prev["date"]), None)
    for r in planned["new"] + planned["versions"] + planned["identity"]:
        cur = open_state.get((r["show_id"], r["date"]), {})
        cur.update({f: r.get(f) for f in ("show_id", "date", "cinema_id", "movie_id") + STATE_FIELDS})
        open_state[(r["show_id"], r["date"])] = cur


def read_raw(raw_path):
    path = config.ROOT / raw_path if not str(raw_path).startswith("/") else raw_path
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def process_snapshot(cur, snap, open_by_chain):
    """Reconstruye una captura buena: crudo → filas → plan → escritura → marca de agua. Sin commit."""
    chain = snap["chain"]
    raw = read_raw(snap["raw_path"])
    rows = normalize.rows(chain, raw)
    open_state = open_by_chain.setdefault(chain, None)
    if open_state is None:
        open_state = open_by_chain[chain] = load_open(cur, chain)
    planned = plan(chain, open_state, rows, snap["taken_at"])
    counts = apply(cur, chain, planned, snap["taken_at"], cinema_cities(chain, raw))
    refresh_open(open_state, planned)
    pg.set_watermark(cur, "showtime", snap["id"])
    counts["rows"] = len(rows)
    return counts
