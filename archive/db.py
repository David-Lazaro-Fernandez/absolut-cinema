"""Conexión de solo lectura al archivo histórico. Mismo DSN y rol que `auth/` (`absolut_app`); aquí además la sesión
nace en `default_transaction_read_only` y con un tope de 15 s por consulta, para que un filtro mal puesto en el
explorador no cuelgue el dashboard."""
import psycopg
from psycopg.rows import dict_row

from scraper import config

STATEMENT_TIMEOUT_MS = 15000


def connect(dsn=None):
    return psycopg.connect(dsn or config.AUTH_PG_DSN, row_factory=dict_row, autocommit=True,
                           options=f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}")


def rows(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
