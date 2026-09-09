"""Diff entre el estado anterior y el snapshot actual de una cadena, por id de función."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .normalize import CHANGE_FIELDS, MOVE_FIELDS


def closing_kind(datetime_local, taken_at):
    """Cómo se cierra una función que dejó de estar publicada en la captura `taken_at` (ISO UTC): `expired` si ya
    había empezado o le faltaban `config.REMOVED_GRACE_MINUTES` o menos (terminó su vida normal), `removed` si aún
    faltaba más (una cancelación). Con hora ilegible se considera `removed`."""
    now_local = datetime.fromisoformat(taken_at).astimezone(ZoneInfo(config.PILOT_TIMEZONE)).replace(tzinfo=None)
    try:
        starts = datetime.fromisoformat(datetime_local)
    except (TypeError, ValueError):
        return "removed"
    return "expired" if starts <= now_local + timedelta(minutes=config.REMOVED_GRACE_MINUTES) else "removed"


def changed_fields(prev, row, fields):
    """Campos de `fields` que difieren entre dos filas de la misma función. Una sala que pasa de desconocida a
    conocida (o al revés) no cuenta: es ausencia de dato, no una mudanza (el 2026-09-08 Cinemex renombró el campo
    de sala y sin esta regla salieron 16,237 cambios falsos)."""
    out = []
    for f in fields:
        a, b = prev.get(f) or None, row.get(f) or None
        if a == b or (f == "screen" and (a is None or b is None)):
            continue
        out.append(f)
    return out


def _strip(row, keep_first_seen=False):
    """Copia de la fila sin `first_seen`. En los eventos de cierre (`removed`, `expired`) se conserva, porque es
    la única huella de cuándo apareció una función que ya no está en current_showtime."""
    return {k: v for k, v in row.items() if keep_first_seen or k != "first_seen"}


def diff(chain, previous, current, snapshot_id, prev_snapshot_id, taken_at):
    """previous/current: {show_id: fila}. Devuelve la lista de eventos detectados."""
    events = []

    def ev(kind, show_id, before, after):
        ref = after or before
        events.append({
            "chain": chain, "show_id": show_id, "kind": kind, "detected_at": taken_at,
            "snapshot_id": snapshot_id, "prev_snapshot_id": prev_snapshot_id,
            "cinema_id": ref.get("cinema_id"), "movie_id": ref.get("movie_id"),
            "movie_title": ref.get("movie_title"), "date": ref.get("date"),
            "datetime_local": ref.get("datetime_local"),
            "before": _strip(before, keep_first_seen=after is None) if before else None,
            "after": _strip(after) if after else None,
        })

    def close(show_id, prev):
        """La función dejó de estar publicada: `expired` o `removed` según `closing_kind`. Ambos guardan la fila
        completa en `before` para poder reconstruir la cartelera de ese día más tarde."""
        ev(closing_kind(prev.get("datetime_local"), taken_at), show_id, prev, None)

    for show_id, row in current.items():
        prev = previous.get(show_id)
        if prev is None:
            ev("added", show_id, None, row)
            continue
        if (prev.get("date") or None) != (row.get("date") or None):
            # Mismo id en otra fecha: Vista recicla ids de sesión. Es una función nueva, no un cambio,
            # y la anterior se cierra para que su día quede reconstruible.
            close(show_id, prev)
            ev("added", show_id, None, row)
            continue
        if changed_fields(prev, row, MOVE_FIELDS):
            ev("moved", show_id, prev, row)
        elif changed_fields(prev, row, CHANGE_FIELDS):
            ev("changed", show_id, prev, row)
        elif changed_fields(prev, row, ("availability",)):
            ev("availability", show_id, prev, row)

    for show_id, prev in previous.items():
        if show_id not in current:
            close(show_id, prev)
    return events
