"""Estado del archivo histórico en PostgreSQL para la página de operaciones: si responde y en cuánto, versión, tamaño,
conexiones abiertas, filas y tamaño por tabla, y hasta dónde llegó el sync por tabla origen.

Solo lectura y sin privilegios especiales: `pg_stat_user_tables`, `pg_class` y `pg_database_size` responden al rol
`absolut_app`. Las tablas particionadas (`showtime`, `showtime_state`, `event`) se suman bajo el nombre del padre; el
conteo de filas es el estimado del planificador (`n_live_tup`), suficiente para detectar que algo dejó de crecer.
"""
import time

from .db import rows


def postgres_status(conn):
    """Un solo dict: latencia de un `SELECT 1` en ms, versión del servidor, base y su tamaño en bytes, y conexiones
    abiertas a esa base."""
    t0 = time.monotonic()
    rows(conn, "SELECT 1")
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    r = rows(conn, """
        SELECT current_database() AS database, current_setting('server_version') AS server_version,
               pg_database_size(current_database()) AS size_bytes,
               (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS connections,
               now() AS server_time""")[0]
    return {"latency_ms": latency_ms, **r}


def table_sizes(conn):
    """Filas estimadas y tamaño total (datos + índices) por tabla del esquema `public`, particiones sumadas bajo su
    padre, en orden alfabético."""
    return rows(conn, """
        SELECT COALESCE(p.relname, c.relname) AS table_name,
               COALESCE(SUM(s.n_live_tup), 0)::bigint AS rows_estimate,
               SUM(pg_total_relation_size(c.oid))::bigint AS size_bytes,
               COUNT(*) FILTER (WHERE i.inhrelid IS NOT NULL) AS partitions
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        LEFT JOIN pg_inherits i ON i.inhrelid = c.oid
        LEFT JOIN pg_class p ON p.oid = i.inhparent
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        GROUP BY 1 ORDER BY 1""")


def sync_watermarks(conn):
    """Hasta qué id de SQLite llegó el sync por tabla origen y cuándo, en orden alfabético."""
    return rows(conn, "SELECT source_table, last_id, synced_at FROM sync_watermark ORDER BY source_table")
