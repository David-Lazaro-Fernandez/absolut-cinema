"""Conexión del dashboard a PostgreSQL con el rol `absolut_app` (escritura solo en el esquema `app`)."""
import psycopg
from psycopg.rows import dict_row

from scraper import config


def connect(dsn=None):
    """Conexión en autocommit: las lecturas sueltas no dejan una transacción abierta y cada flujo de `auth.flows`
    agrupa sus escrituras con `conn.transaction()`, que sigue siendo atómico."""
    return psycopg.connect(dsn or config.AUTH_PG_DSN, row_factory=dict_row, autocommit=True)


def rows(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()
