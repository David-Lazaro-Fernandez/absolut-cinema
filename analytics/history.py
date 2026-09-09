"""Historia de la cartelera: qué funciones hubo en un cine y un día, qué le pasó a cada una y cómo estaba
la cartelera en un momento de captura dado.

Fuentes: `current_showtime` (estado vigente) y `event` (cada cambio con la fila completa antes y después;
`removed`/`expired` cierran una función y conservan su `first_seen`). La reconstrucción "tal como estaba" es un
replay inverso de los eventos posteriores al instante pedido; es exacta desde que existe el evento `expired`
(2026-09-09). Para fechas anteriores la fuente completa es el crudo gz de cada snapshot.
"""
import json

from .db import rows

# Campos que cuentan como cambio en la línea de tiempo (mismos que el diff del scraper, más la ocupación).
TRACKED_FIELDS = ("datetime_local", "screen", "language", "format", "experience", "premium_tier", "movie_id", "availability")
CLOSING_KINDS = ("removed", "expired")


def cinemas(conn, chain="cinemex"):
    """Cines con cartelera vigente: `cinema_id`, `cinema_name`, ordenados por nombre."""
    return rows(conn, """
        SELECT cinema_id, MAX(cinema_name) cinema_name FROM current_showtime WHERE chain = ?
        GROUP BY cinema_id ORDER BY cinema_name""", (chain,))


def dates_known(conn, chain, cinema_id):
    """Fechas con funciones conocidas de ese cine: vigentes o cerradas por un evento. Orden ascendente."""
    return rows(conn, """
        SELECT date FROM current_showtime WHERE chain = ? AND cinema_id = ?
        UNION SELECT date FROM event WHERE chain = ? AND cinema_id = ? AND date IS NOT NULL
        ORDER BY date""", (chain, cinema_id, chain, cinema_id))


def functions_on(conn, chain, cinema_id, date):
    """Funciones conocidas de un cine en una fecha: las vigentes más las cerradas (`status` = current | removed |
    expired), con la última fila conocida de cada una y su `first_seen`. Orden: hora, sala."""
    current = rows(conn, """
        SELECT *, 'current' status FROM current_showtime WHERE chain = ? AND cinema_id = ? AND date = ?""", (chain, cinema_id, date))
    seen = {r["show_id"] for r in current}
    closed = rows(conn, """
        SELECT show_id, kind, before_json FROM (
            SELECT show_id, kind, before_json, ROW_NUMBER() OVER (PARTITION BY show_id ORDER BY id DESC) rk
            FROM event WHERE chain = ? AND cinema_id = ? AND date = ? AND kind IN ('removed', 'expired'))
        WHERE rk = 1""", (chain, cinema_id, date))
    out = list(current)
    for r in closed:
        if r["show_id"] in seen or not r["before_json"]:
            continue
        row = json.loads(r["before_json"])
        row["status"] = r["kind"]
        row.setdefault("first_seen", None)
        out.append(row)
    return sorted(out, key=lambda r: (r.get("datetime_local") or "", r.get("screen") or ""))


def showtime_timeline(conn, chain, show_id, date):
    """Eventos de una función, del más antiguo al más reciente: `detected_at`, `kind`, `snapshot_id` y `changes`
    (lista de {field, before, after} sobre TRACKED_FIELDS; vacía en altas y cierres). El primer elemento es
    siempre la primera aparición (`kind='first_seen'`), tomada de la función vigente, del cierre o del primer alta."""
    events = rows(conn, """
        SELECT id, kind, detected_at, snapshot_id, before_json, after_json FROM event
        WHERE chain = ? AND show_id = ? AND date = ? ORDER BY id""", (chain, show_id, date))
    first_seen = None
    cur = rows(conn, "SELECT first_seen FROM current_showtime WHERE chain = ? AND show_id = ? AND date = ?", (chain, show_id, date))
    if cur:
        first_seen = cur[0]["first_seen"]
    out = []
    for e in events:
        before = json.loads(e["before_json"]) if e["before_json"] else None
        after = json.loads(e["after_json"]) if e["after_json"] else None
        if not first_seen and before and before.get("first_seen"):
            first_seen = before["first_seen"]
        changes = []
        if before and after:
            changes = [{"field": f, "before": before.get(f), "after": after.get(f)}
                       for f in TRACKED_FIELDS if (before.get(f) or None) != (after.get(f) or None)]
        out.append({"detected_at": e["detected_at"], "kind": e["kind"], "snapshot_id": e["snapshot_id"], "changes": changes})
    if not first_seen:
        first_seen = next((e["detected_at"] for e in out if e["kind"] == "added"), None)
    if first_seen:
        out.insert(0, {"detected_at": first_seen, "kind": "first_seen", "snapshot_id": None, "changes": []})
    return out


def snapshot_times(conn, chain, since, until):
    """Capturas buenas de la cadena entre dos instantes (ISO, UTC): `id`, `taken_at`, `n_shows`. Ascendente."""
    return rows(conn, """
        SELECT id, taken_at, n_shows FROM snapshot WHERE chain = ? AND ok = 1 AND taken_at BETWEEN ? AND ? ORDER BY id""",
                (chain, since, until))


def board_as_of(conn, chain, cinema_id, date, as_of):
    """Cartelera de un cine y un día tal como estaba publicada en el instante `as_of` (ISO, UTC; usar el
    `taken_at` de una captura). Replay inverso desde el estado vigente: se quitan las altas posteriores, se
    restauran las funciones cerradas después y se revierten los cambios posteriores. Cada fila trae
    `vs_now` = same | changed | gone (ya no está publicada) y `changed_fields`. Orden: hora, sala."""
    now_rows = {r["show_id"]: dict(r) for r in rows(conn, "SELECT * FROM current_showtime WHERE chain = ? AND cinema_id = ? AND date = ?",
                                                     (chain, cinema_id, date))}
    state = {k: dict(v) for k, v in now_rows.items()}
    later = rows(conn, """
        SELECT show_id, kind, before_json FROM event
        WHERE chain = ? AND cinema_id = ? AND date = ? AND detected_at > ? ORDER BY id DESC""", (chain, cinema_id, date, as_of))
    for e in later:
        if e["kind"] == "added":
            state.pop(e["show_id"], None)
        elif e["before_json"]:
            state[e["show_id"]] = json.loads(e["before_json"])
    out = []
    for show_id, row in state.items():
        now = now_rows.get(show_id)
        if not now:
            row["vs_now"], row["changed_fields"] = "gone", []
        else:
            diff = [f for f in TRACKED_FIELDS if (row.get(f) or None) != (now.get(f) or None)]
            row["vs_now"], row["changed_fields"] = ("changed" if diff else "same"), diff
        out.append(row)
    return sorted(out, key=lambda r: (r.get("datetime_local") or "", r.get("screen") or ""))
