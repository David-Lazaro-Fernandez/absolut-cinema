"""Sesiones (`app.session`): una fila por cookie emitida. El valor de la cookie nunca se guarda, solo su sha256."""
from datetime import datetime, timedelta, timezone

from . import security
from .db import one

_USER = "a.id, a.email, a.name, a.role::text AS role, a.active"


def create(conn, user_id, ip=None, user_agent=None, now=None):
    """Emite una sesión y devuelve el valor en claro para la cookie."""
    now = now or datetime.now(timezone.utc)
    raw, token_hash = security.new_token()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO app.session (token_hash, account_id, created_at, last_seen_at, expires_at, ip, user_agent)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (token_hash, user_id, now, now, now + timedelta(days=security.SESSION_TTL_DAYS), ip,
                     (user_agent or "")[:300] or None))
    return raw


def current_session(conn, raw, now=None):
    """Usuario de una cookie vigente (cuenta activa, sesión no revocada ni caducada) o None. Extiende la vigencia
    cuando la última visita tiene más de `SESSION_TOUCH_MINUTES`, para no escribir en cada corrida."""
    if not raw:
        return None
    now = now or datetime.now(timezone.utc)
    token_hash = security.hash_token(raw)
    row = one(conn, f"""SELECT {_USER}, s.last_seen_at
                        FROM app.session s JOIN app.account a ON a.id = s.account_id
                        WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > %s AND a.active""",
              (token_hash, now))
    if row is None:
        return None
    if now - row["last_seen_at"] > timedelta(minutes=security.SESSION_TOUCH_MINUTES):
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("UPDATE app.session SET last_seen_at = %s, expires_at = %s WHERE token_hash = %s",
                            (now, now + timedelta(days=security.SESSION_TTL_DAYS), token_hash))
    return {k: row[k] for k in ("id", "email", "name", "role", "active")}


def revoke(conn, raw, now=None):
    """Cierra la sesión de una cookie. Devuelve el id de la cuenta o None si no había sesión vigente."""
    row = one(conn, """UPDATE app.session SET revoked_at = %s
                       WHERE token_hash = %s AND revoked_at IS NULL RETURNING account_id""",
              (now or datetime.now(timezone.utc), security.hash_token(raw or "")))
    return row["account_id"] if row else None


def revoke_all(conn, user_id, now=None):
    with conn.cursor() as cur:
        cur.execute("UPDATE app.session SET revoked_at = %s WHERE account_id = %s AND revoked_at IS NULL",
                    (now or datetime.now(timezone.utc), user_id))


def prune(conn, keep_days=90):
    """Borra sesiones y tokens caducados o revocados hace más de `keep_days`. Devuelve (sesiones, tokens)."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""DELETE FROM app.session
                           WHERE coalesce(revoked_at, expires_at) < now() - make_interval(days => %s)""", (keep_days,))
            n_sessions = cur.rowcount
            cur.execute("""DELETE FROM app.token
                           WHERE coalesce(used_at, expires_at) < now() - make_interval(days => %s)""", (keep_days,))
            return n_sessions, cur.rowcount
