"""Diff entre el estado anterior y el snapshot actual de una cadena, por id de función."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .normalize import CHANGE_FIELDS, MOVE_FIELDS


def _strip(row, keep_first_seen=False):
    """Copia de la fila sin `first_seen`. En los eventos de cierre (`removed`, `expired`) se conserva, porque es
    la única huella de cuándo apareció una función que ya no está en current_showtime."""
    return {k: v for k, v in row.items() if keep_first_seen or k != "first_seen"}


def diff(chain, previous, current, snapshot_id, prev_snapshot_id, taken_at):
    """previous/current: {show_id: fila}. Devuelve la lista de eventos detectados."""
    now_local = datetime.fromisoformat(taken_at).astimezone(ZoneInfo(config.PILOT_TIMEZONE)).replace(tzinfo=None)
    grace_cutoff = now_local + timedelta(minutes=config.REMOVED_GRACE_MINUTES)
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
        """La función dejó de estar publicada. Si ya empezó (o está por empezar) es `expired`: terminó su
        vida normal. Si faltaban más de 30 min, es `removed`: una cancelación. Ambos guardan la fila
        completa en `before` para poder reconstruir la cartelera de ese día más tarde."""
        try:
            starts = datetime.fromisoformat(prev["datetime_local"])
        except (TypeError, ValueError):
            starts = None
        ev("expired" if starts is not None and starts <= grace_cutoff else "removed", show_id, prev, None)

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
        # Una sala que pasa de desconocida a conocida (o al revés) es ausencia de dato, no una mudanza:
        # el 2026-09-08 Cinemex renombró el campo de sala y sin esta regla salieron 16,237 "moved" falsos.
        moved = any(
            (prev.get(f) or None) != (row.get(f) or None)
            and not (f == "screen" and (not prev.get(f) or not row.get(f)))
            for f in MOVE_FIELDS
        )
        if moved:
            ev("moved", show_id, prev, row)
        elif any((prev.get(f) or None) != (row.get(f) or None) for f in CHANGE_FIELDS):
            ev("changed", show_id, prev, row)
        elif (prev.get("availability") or None) != (row.get("availability") or None):
            ev("availability", show_id, prev, row)

    for show_id, prev in previous.items():
        if show_id not in current:
            close(show_id, prev)
    return events
