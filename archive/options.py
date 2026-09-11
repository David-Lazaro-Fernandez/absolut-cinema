"""Listas para los filtros del explorador: cines por cadena y categorías de cada tabla de precios."""
from .db import rows
from .sql import where

_CATEGORY_TABLES = {"concession_prices": "concession_price", "delivery_prices": "delivery_price"}


def cinema_options(conn, chain=None):
    """[{chain, cinema_id, cinema_name}] ordenados por cadena y nombre."""
    w, p = where([("chain = %s::chain_t", chain)])
    return rows(conn, f"SELECT chain::text AS chain, cinema_id, name AS cinema_name FROM cinema {w} ORDER BY chain, name", p)


def categories(conn, dataset):
    """Categorías distintas de la tabla de precios de un dataset, ordenadas."""
    table = _CATEGORY_TABLES[dataset]
    return [r["category"] for r in rows(conn, f"SELECT DISTINCT category FROM {table} WHERE category IS NOT NULL ORDER BY 1")]
