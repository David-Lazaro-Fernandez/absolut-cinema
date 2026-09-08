"""Diff entre el estado anterior y el snapshot actual de una cadena, por id de función."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .normalize import CHANGE_FIELDS, MOVE_FIELDS


def _strip(row):
    return {k: v for k, v in row.items() if k != "first_seen"}


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
            "before": _strip(before) if before else None,
            "after": _strip(after) if after else None,
        })

    for show_id, row in current.items():
        prev = previous.get(show_id)
        if prev is None:
            ev("added", show_id, None, row)
            continue
        if (prev.get("date") or None) != (row.get("date") or None):
            # Mismo id en otra fecha: Vista recicla ids de sesión. Es una función nueva, no un cambio.
            ev("added", show_id, None, row)
            continue
        if any((prev.get(f) or None) != (row.get(f) or None) for f in MOVE_FIELDS):
            ev("moved", show_id, prev, row)
        elif any((prev.get(f) or None) != (row.get(f) or None) for f in CHANGE_FIELDS):
            ev("changed", show_id, prev, row)
        elif (prev.get("availability") or None) != (row.get("availability") or None):
            ev("availability", show_id, prev, row)

    for show_id, prev in previous.items():
        if show_id in current:
            continue
        try:
            starts = datetime.fromisoformat(prev["datetime_local"])
        except (TypeError, ValueError):
            starts = None
        # Si ya empezó (o está por empezar) simplemente expiró; no es una eliminación.
        if starts is not None and starts <= grace_cutoff:
            continue
        ev("removed", show_id, prev, None)
    return events
