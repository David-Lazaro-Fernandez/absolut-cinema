"""Cuentas (`app.account`): altas, consulta, rol, activación y registro de accesos. Las funciones reciben la
conexión y no cierran la transacción; eso lo hace `auth.flows`."""
from datetime import datetime, timezone

from . import security
from .db import one, rows
from .errors import DuplicateEmail, LastAdmin, SelfChange

_COLUMNS = """id, email, name, role::text AS role, password_hash IS NOT NULL AS has_password, active, created_at,
              created_by, last_login_at, failed_logins, last_failed_at, locked_until"""


def create(conn, email, name, role="viewer", created_by=None):
    """Cuenta nueva sin contraseña (la fija al aceptar la invitación). Levanta `DuplicateEmail`."""
    email = security.normalize_email(email)
    if by_email(conn, email):
        raise DuplicateEmail(email)
    return one(conn, f"""INSERT INTO app.account (email, name, role, created_by) VALUES (%s, %s, %s::app.role_t, %s)
                         RETURNING {_COLUMNS}""", (email, name.strip(), role, created_by))


def by_email(conn, email):
    return one(conn, f"SELECT {_COLUMNS} FROM app.account WHERE lower(email) = %s", (security.normalize_email(email),))


def by_id(conn, user_id):
    return one(conn, f"SELECT {_COLUMNS} FROM app.account WHERE id = %s", (user_id,))


def password_hash(conn, user_id):
    row = one(conn, "SELECT password_hash FROM app.account WHERE id = %s", (user_id,))
    return row["password_hash"] if row else None


def list_users(conn):
    """Todas las cuentas con si tienen invitación pendiente, ordenadas por nombre. Nunca devuelve el hash."""
    return rows(conn, f"""
        SELECT {_COLUMNS},
               EXISTS (SELECT 1 FROM app.token t
                       WHERE t.account_id = a.id AND t.purpose = 'invite' AND t.used_at IS NULL AND t.expires_at > now())
                 AS pending_invite
        FROM app.account a
        ORDER BY active DESC, name, email""")


def _active_admins(conn):
    return one(conn, "SELECT count(*) AS n FROM app.account WHERE role = 'admin' AND active")["n"]


def set_active(conn, actor_id, user_id, active):
    """Activa o desactiva; nadie se desactiva a sí mismo ni al último admin activo."""
    if actor_id == user_id:
        raise SelfChange()
    target = by_id(conn, user_id)
    if not active and target["role"] == "admin" and target["active"] and _active_admins(conn) <= 1:
        raise LastAdmin()
    with conn.cursor() as cur:
        cur.execute("UPDATE app.account SET active = %s WHERE id = %s", (active, user_id))


def set_role(conn, actor_id, user_id, role):
    if actor_id == user_id:
        raise SelfChange()
    target = by_id(conn, user_id)
    if role != "admin" and target["role"] == "admin" and target["active"] and _active_admins(conn) <= 1:
        raise LastAdmin()
    with conn.cursor() as cur:
        cur.execute("UPDATE app.account SET role = %s::app.role_t WHERE id = %s", (role, user_id))


def set_password(conn, user_id, password):
    """Guarda el hash y desbloquea la cuenta. Quien llama debe revocar las sesiones (auth.sessions.revoke_all)."""
    with conn.cursor() as cur:
        cur.execute("""UPDATE app.account SET password_hash = %s, failed_logins = 0, locked_until = NULL
                       WHERE id = %s""", (security.hash_password(password), user_id))


def record_login(conn, user_id, ok, now=None):
    """Éxito: reinicia el contador y anota `last_login_at`. Fallo: suma uno y, al llegar al tope, fija
    `locked_until`. Devuelve el instante de bloqueo (o None)."""
    now = now or datetime.now(timezone.utc)
    with conn.cursor() as cur:
        if ok:
            cur.execute("""UPDATE app.account SET failed_logins = 0, locked_until = NULL, last_login_at = %s
                           WHERE id = %s""", (now, user_id))
            return None
        cur.execute("""UPDATE app.account SET failed_logins = failed_logins + 1, last_failed_at = %s
                       WHERE id = %s RETURNING failed_logins""", (now, user_id))
        fails = cur.fetchone()["failed_logins"]
        until = security.locked_until(fails, now)
        if until:
            cur.execute("UPDATE app.account SET locked_until = %s, failed_logins = 0 WHERE id = %s", (until, user_id))
        return until
