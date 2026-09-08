"""Consultas de negocio sobre data/snapshots.db.

Funciones puras: reciben una conexión SQLite y parámetros, devuelven listas de dicts.
Sin dependencias fuera de la librería estándar, para que el dashboard (Streamlit) y un
futuro API (FastAPI) llamen exactamente lo mismo. Los textos para usuarios viven en labels.py.
"""
from . import labels
from .db import connect
from .findings import conclusions, findings
from .headlines import headlines
from .seats import (
    capacity_by_cinema,
    capacity_summary,
    estimated_occupancy,
    occupancy_recent,
    occupancy_summary,
    offered_by_title,
    offered_seats,
    prices,
    semaphore_calibration,
)
from .queries import (
    cinema_week,
    concentration,
    coverage,
    events_by_kind,
    heatmap_day_slot,
    kpis,
    kpis_today,
    mix,
    movies_by_chain,
    recent_events,
    showtimes_by_slot,
    snapshot_health,
    today,
)

__all__ = [
    "capacity_by_cinema", "capacity_summary", "estimated_occupancy", "occupancy_recent", "occupancy_summary",
    "offered_by_title", "offered_seats", "prices", "semaphore_calibration",
    "cinema_week", "concentration", "conclusions", "connect", "coverage", "events_by_kind", "findings", "headlines",
    "heatmap_day_slot", "kpis", "kpis_today", "labels", "mix", "movies_by_chain", "recent_events",
    "showtimes_by_slot", "snapshot_health", "today",
]
