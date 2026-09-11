"""Consultas de negocio sobre data/snapshots.db.

Funciones puras: reciben una conexión SQLite y parámetros, devuelven listas de dicts.
Sin dependencias fuera de la librería estándar, para que el dashboard (Streamlit) y un
futuro API (FastAPI) llamen exactamente lo mismo. Los textos para usuarios viven en labels.py.
"""
from . import labels
from .concessions import (
    BASKET,
    concession_basket,
    concession_by_cinema,
    concession_categories,
    concession_product_by_cinema,
    concession_summary,
)
from .db import connect
from .delivery import (
    DELIVERY_BUCKETS,
    delivery_compare,
    delivery_products,
    delivery_stores,
    delivery_summary,
)
from .findings import conclusions, findings
from .headlines import headlines
from .history import board_as_of, cinemas, dates_known, functions_on, showtime_timeline, snapshot_times
from .queries import (
    cinema_week,
    concentration,
    coverage,
    events_by_kind,
    heatmap_day_slot,
    is_full_day,
    kpis,
    kpis_today,
    mix,
    movies_by_chain,
    recent_events,
    showtimes_by_slot,
    snapshot_health,
    today,
)
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
from .summary import general_summary

__all__ = [
    "board_as_of", "cinemas", "dates_known", "functions_on", "showtime_timeline", "snapshot_times",
    "general_summary",
    "DELIVERY_BUCKETS", "delivery_compare", "delivery_products", "delivery_stores", "delivery_summary",
    "BASKET", "concession_basket", "concession_by_cinema", "concession_categories", "concession_product_by_cinema", "concession_summary",
    "capacity_by_cinema", "capacity_summary", "estimated_occupancy", "occupancy_recent", "occupancy_summary",
    "offered_by_title", "offered_seats", "prices", "semaphore_calibration",
    "cinema_week", "concentration", "conclusions", "connect", "coverage", "events_by_kind", "findings", "headlines",
    "heatmap_day_slot", "is_full_day", "kpis", "kpis_today", "labels", "mix", "movies_by_chain", "recent_events",
    "showtimes_by_slot", "snapshot_health", "today",
]
