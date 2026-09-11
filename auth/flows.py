"""Flujos de acceso que comparten las páginas del dashboard y la línea de comandos: entrar, salir, invitar,
restablecer contraseña y administrar cuentas. Cada función cierra su propia transacción (`conn.transaction()`) y deja
rastro en `app.audit`. Sin Streamlit."""
import json
from datetime import datetime, timedelta, timezone

from analytics.labels import MAIL_INVITE, MAIL_RESET
from scraper import config

from . import mail, security, sessions, users
from .db import one
from .errors import AccountInactive, AccountLocked, InvalidCredentials, MailFailed, TokenInvalid, WeakPassword


def link_for(raw):
    """URL pública del enlace de un token (invitación o restablecimiento)."""
    return f"{config.BASE_URL}/restablecer?token={raw}"


def login(conn, email, password, ip=None, user_agent=None):
    """Verifica credenciales y emite una sesión. Devuelve (valor de la cookie, usuario). Levanta
    `InvalidCredentials`, `AccountInactive` o `AccountLocked`. Un correo desconocido cuesta lo mismo que una
    contraseña mala: se verifica contra un hash falso para no revelar cuentas por tiempo de respuesta. El registro
    del fallo se confirma antes de levantar el error, para que el contador de bloqueo no se deshaga."""
    now = datetime.now(timezone.utc)
    failure = None
    with conn.transaction():
        user = users.by_email(conn, email)
        if user is None:
            security.verify_password(password, _DUMMY_HASH)
            _audit(conn, None, "login_failed", None, {"email": security.normalize_email(email), "ip": ip})
            failure = InvalidCredentials()
        elif user["locked_until"] and user["locked_until"] > now:
            failure = AccountLocked(security.minutes_left(user["locked_until"], now))
        elif not security.verify_password(password, users.password_hash(conn, user["id"])):
            until = users.record_login(conn, user["id"], ok=False, now=now)
            _audit(conn, user["id"], "login_failed", user["id"], {"ip": ip, "locked": until is not None})
            failure = AccountLocked(security.minutes_left(until, now)) if until else InvalidCredentials()
        elif not user["active"]:
            failure = AccountInactive()
        else:
            users.record_login(conn, user["id"], ok=True, now=now)
            raw = sessions.create(conn, user["id"], ip=ip, user_agent=user_agent, now=now)
            _audit(conn, user["id"], "login_ok", user["id"], {"ip": ip})
    if failure:
        raise failure
    return raw, {k: user[k] for k in ("id", "email", "name", "role", "active")}


def logout(conn, raw):
    with conn.transaction():
        user_id = sessions.revoke(conn, raw)
        if user_id:
            _audit(conn, user_id, "logout", user_id, None)


def invite(conn, actor_id, email, name, role="viewer", send_mail=True):
    """Crea la cuenta y su enlace de invitación; lo envía por correo salvo `send_mail=False`. Devuelve
    (usuario, enlace). Levanta `DuplicateEmail`."""
    with conn.transaction():
        user = users.create(conn, email, name, role, created_by=actor_id)
        raw = _issue_token(conn, user["id"], "invite", actor_id)
        _audit(conn, actor_id, "invite", user["id"], {"role": role})
    link = link_for(raw)
    if send_mail:
        _send(user, MAIL_INVITE, link, hours=security.INVITE_TTL_HOURS)
    return user, link


def resend(conn, actor_id, user_id, send_mail=True):
    """Enlace nuevo para una cuenta (invitación si aún no tiene contraseña, restablecimiento si ya la tiene).
    Invalida los enlaces anteriores. Devuelve el enlace."""
    with conn.transaction():
        user = users.by_id(conn, user_id)
        purpose = "reset" if user["has_password"] else "invite"
        raw = _issue_token(conn, user_id, purpose, actor_id)
        _audit(conn, actor_id, "resend", user_id, {"purpose": purpose})
    link = link_for(raw)
    if send_mail:
        if purpose == "invite":
            _send(user, MAIL_INVITE, link, hours=security.INVITE_TTL_HOURS)
        else:
            _send(user, MAIL_RESET, link, minutes=security.RESET_TTL_MIN)
    return link


def request_reset(conn, email, send_mail=True):
    """Flujo público de "olvidé mi contraseña". Silencioso: si el correo no existe, la cuenta está inactiva o ya
    pidió `RESET_MAX_PER_HOUR` enlaces en la última hora, no hace nada y devuelve None. Si no, devuelve el enlace
    (solo lo muestra la línea de comandos; la página nunca lo pinta)."""
    now = datetime.now(timezone.utc)
    with conn.transaction():
        user = users.by_email(conn, email)
        if user is None or not user["active"]:
            return None
        recent = one(conn, """SELECT count(*) AS n FROM app.token
                              WHERE account_id = %s AND purpose = 'reset' AND created_at > %s""",
                     (user["id"], now - timedelta(hours=1)))["n"]
        if recent >= security.RESET_MAX_PER_HOUR:
            return None
        raw = _issue_token(conn, user["id"], "reset", None, now=now)
        _audit(conn, user["id"], "reset_requested", user["id"], None)
    link = link_for(raw)
    if send_mail:
        _send(user, MAIL_RESET, link, minutes=security.RESET_TTL_MIN)
    return link


def peek_token(conn, raw):
    """Datos del enlace antes de usarlo (propósito y correo de la cuenta), para que la página sepa qué texto
    mostrar. Levanta `TokenInvalid` si no sirve."""
    token = _token(conn, raw)
    return {"purpose": token["purpose"], "email": token["email"], "name": token["name"], "account_id": token["account_id"]}


def redeem_token(conn, raw, password):
    """Fija la contraseña con un enlace válido, lo marca como usado y cierra todas las sesiones de la cuenta.
    Devuelve el usuario. Levanta `TokenInvalid` o `WeakPassword`."""
    now = datetime.now(timezone.utc)
    with conn.transaction():
        token = _token(conn, raw, now)
        problem = security.check_strength(password, token["email"])
        if problem:
            raise WeakPassword(problem)
        users.set_password(conn, token["account_id"], password)
        sessions.revoke_all(conn, token["account_id"], now)
        with conn.cursor() as cur:
            cur.execute("UPDATE app.token SET used_at = %s WHERE token_hash = %s", (now, token["token_hash"]))
        _audit(conn, token["account_id"], "set_password", token["account_id"], {"via": token["purpose"]})
        return users.by_id(conn, token["account_id"])


def deactivate(conn, actor_id, user_id):
    with conn.transaction():
        users.set_active(conn, actor_id, user_id, False)
        sessions.revoke_all(conn, user_id)
        _audit(conn, actor_id, "deactivate", user_id, None)


def activate(conn, actor_id, user_id):
    with conn.transaction():
        users.set_active(conn, actor_id, user_id, True)
        _audit(conn, actor_id, "activate", user_id, None)


def set_role(conn, actor_id, user_id, role):
    with conn.transaction():
        users.set_role(conn, actor_id, user_id, role)
        _audit(conn, actor_id, "set_role", user_id, {"role": role})


# --- privado ---------------------------------------------------------------------------------------
# Hash de una contraseña aleatoria: contra él se verifica cuando el correo no existe, para que el tiempo de
# respuesta no delate qué cuentas hay.
_DUMMY_HASH = security.hash_password(security.new_token()[0])


def _issue_token(conn, user_id, purpose, created_by, now=None):
    """Invalida los enlaces vigentes del mismo propósito y emite uno nuevo. Devuelve el valor en claro."""
    now = now or datetime.now(timezone.utc)
    ttl = timedelta(hours=security.INVITE_TTL_HOURS) if purpose == "invite" else timedelta(minutes=security.RESET_TTL_MIN)
    raw, token_hash = security.new_token()
    with conn.cursor() as cur:
        cur.execute("""UPDATE app.token SET used_at = %s
                       WHERE account_id = %s AND purpose = %s AND used_at IS NULL""", (now, user_id, purpose))
        cur.execute("""INSERT INTO app.token (token_hash, account_id, purpose, created_at, expires_at, created_by)
                       VALUES (%s, %s, %s, %s, %s, %s)""", (token_hash, user_id, purpose, now, now + ttl, created_by))
    return raw


def _token(conn, raw, now=None):
    token = one(conn, """SELECT t.token_hash, t.account_id, t.purpose, t.expires_at, t.used_at, a.email, a.name
                         FROM app.token t JOIN app.account a ON a.id = t.account_id
                         WHERE t.token_hash = %s AND a.active""", (security.hash_token(raw or ""),))
    if not security.is_usable(token, now):
        raise TokenInvalid()
    return token


def _send(user, template, link, **ttl):
    """Manda el enlace. Si el correo falla, levanta `MailFailed` con el enlace: la cuenta y el token ya existen."""
    ctx = {"name": user["name"], "link": link, **ttl}
    try:
        mail.send(user["email"], template["subject"], template["text"].format(**ctx), template["html"].format(**ctx))
    except Exception as e:  # boto3 tiene su propia jerarquía; aquí solo importa que no salió
        raise MailFailed(link, e) from e


def _audit(conn, actor_id, action, target_id, detail):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO app.audit (actor_id, action, target_id, detail) VALUES (%s, %s, %s, %s)",
                    (actor_id, action, target_id, json.dumps(detail) if detail is not None else None))
