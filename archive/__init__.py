"""Consultas de solo lectura sobre el archivo histórico en PostgreSQL (esquema `public`, el que escribe `sync/`).

Mismo estilo que `analytics/`: funciones puras `fn(conn, ...) -> list[dict]` con `ORDER BY` explícito y filtros con
nombre, pensadas para envolverlas después en un API. Corre en el venv (psycopg) con el rol `absolut_app`, que solo
tiene SELECT aquí; la conexión además fuerza `default_transaction_read_only`. Hoy alimenta el explorador de datos
(`views/datos.py`); la etapa 2 (analytics sobre Postgres) crecerá en este paquete.
"""
from .datasets import (
                       DATASETS,
                       MAX_ROWS,
                       auditoriums,
                       cinemas,
                       concession_prices,
                       delivery_prices,
                       ticket_prices,
                       week_showtimes,
)
from .db import connect, rows
from .options import categories, cinema_options

__all__ = ["DATASETS", "MAX_ROWS", "auditoriums", "categories", "cinema_options", "cinemas", "concession_prices",
           "connect", "delivery_prices", "rows", "ticket_prices", "week_showtimes"]
