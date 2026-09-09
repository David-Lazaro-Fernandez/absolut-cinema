"""Conexión a PostgreSQL, marcas de agua y particiones mensuales del archivo histórico."""
from datetime import date, datetime, timezone

import psycopg
from psycopg import sql

from scraper import config


def connect(dsn=None):
    """Conexión sin autocommit: cada paso del sync decide dónde termina su transacción."""
    return psycopg.connect(dsn or config.PG_DSN)


def watermark(cur, source_table):
    """Último id (o id de snapshot) ya copiado de esa tabla origen; 0 si nunca se copió."""
    cur.execute("SELECT last_id FROM sync_watermark WHERE source_table = %s", (source_table,))
    row = cur.fetchone()
    return int(row[0]) if row else 0


def set_watermark(cur, source_table, last_id):
    cur.execute("""INSERT INTO sync_watermark (source_table, last_id, synced_at) VALUES (%s, %s, now())
                   ON CONFLICT (source_table) DO UPDATE SET last_id = EXCLUDED.last_id, synced_at = now()""",
                (source_table, int(last_id)))


def month_range(d):
    """(primer día del mes, primer día del mes siguiente) de una fecha."""
    first = d.replace(day=1)
    nxt = (first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1))
    return first, nxt


def ensure_partitions(cur, table, dates, column_kind="date"):
    """Crea, si faltan, las particiones mensuales de `table` que cubren `dates` (fechas o instantes) y el mes
    siguiente al mayor, para que la próxima corrida no falle en el cambio de mes. Para `timestamptz` los límites
    van en UTC explícito (la sesión puede estar en America/Mexico_City)."""
    months = set()
    for d in dates:
        if d is None:
            continue
        if isinstance(d, datetime):
            d = d.astimezone(timezone.utc).date()
        months.add(month_range(d)[0])
    if not months:
        return
    months.add(month_range(max(months))[1])
    for first in sorted(months):
        lo, hi = month_range(first)
        name = f"{table}_{first:%Y%m}"
        if column_kind == "timestamptz":
            lo_v, hi_v = f"{lo.isoformat()} 00:00:00+00", f"{hi.isoformat()} 00:00:00+00"
        else:
            lo_v, hi_v = lo.isoformat(), hi.isoformat()
        # DDL: los límites van como literales, no como parámetros (Postgres no los acepta en CREATE TABLE).
        cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} PARTITION OF {} FOR VALUES FROM ({}) TO ({})")
                    .format(sql.Identifier(name), sql.Identifier(table), sql.Literal(lo_v), sql.Literal(hi_v)))


def to_ts(iso):
    """ISO con offset → datetime con zona (timestamptz)."""
    return datetime.fromisoformat(iso) if iso else None


def to_local(iso):
    """'YYYY-MM-DDTHH:MM:SS' sin zona → datetime naive (timestamp, hora local de la plaza)."""
    return datetime.fromisoformat(iso[:19]) if iso else None


def to_date(iso):
    return date.fromisoformat(iso[:10]) if iso else None


def to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_int(v):
    try:
        return int(round(float(v))) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
