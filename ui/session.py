"""Pegamento entre Streamlit y `auth/`: la cookie de sesión, el usuario de la corrida y los formularios de acceso.

Único módulo de la presentación que conoce la cookie `ac_session`. Streamlit solo lee cookies (`st.context.cookies`,
fijadas en el handshake del WebSocket) y no tiene API para escribirlas, así que se escriben con JavaScript desde un
iframe del mismo origen (`st.iframe`) y después se recarga la página: un `st.rerun()` no bastaría porque la cookie
nueva no viaja hasta la siguiente conexión.
"""
import time

import psycopg
import streamlit as st

import auth
from analytics.labels import AUTH_TEXT, ROLE_LABEL
from auth.security import SESSION_TTL_DAYS
from scraper import config

COOKIE = "ac_session"
_MEMO_SECONDS = 60      # cada cuánto se vuelve a validar la sesión en Postgres; acota el efecto de una revocación


def current_user():
    """Usuario de la cookie vigente o None. Consulta Postgres a lo más cada `_MEMO_SECONDS` por pestaña."""
    raw = _raw_cookie()
    if not raw:
        st.session_state.pop("auth", None)
        return None
    memo = st.session_state.get("auth")
    if memo and memo["raw"] == raw and time.time() - memo["checked_at"] < _MEMO_SECONDS:
        return memo["user"]
    user = _with_conn(lambda conn: auth.current_session(conn, raw))
    if user is None:
        st.session_state.pop("auth", None)
        return None
    st.session_state["auth"] = {"raw": raw, "user": user, "checked_at": time.time()}
    return user


def sign_in(email, password):
    """Formulario de entrada enviado: entra y recarga con la cookie puesta, o pinta el error."""
    try:
        raw, _ = _with_conn(lambda conn: auth.login(conn, email, password, ip=client_ip(), user_agent=_user_agent()))
    except auth.AuthError as e:
        st.error(error_text(e))
        return
    _set_cookie_and_reload(raw)


def sign_out():
    raw = _raw_cookie()
    if raw:
        _with_conn(lambda conn: auth.logout(conn, raw))
    st.session_state.pop("auth", None)
    _clear_cookie_and_reload()


def request_reset(email):
    """Pide el enlace; el resultado no se muestra (la página responde igual exista o no la cuenta). Un fallo del
    correo tampoco se revela al visitante: queda en el log de Streamlit."""
    try:
        _with_conn(lambda conn: auth.request_reset(conn, email))
    except auth.MailFailed as e:
        print(f"correo de restablecimiento no enviado: {e.cause}", flush=True)


def peek_token(raw):
    """Datos del enlace (propósito, correo) o None si no sirve."""
    try:
        return _with_conn(lambda conn: auth.peek_token(conn, raw))
    except auth.TokenInvalid:
        return None


def redeem_token(raw, password):
    """Fija la contraseña; devuelve None si salió bien o el texto del error."""
    try:
        _with_conn(lambda conn: auth.redeem_token(conn, raw, password))
    except auth.AuthError as e:
        return error_text(e)
    st.session_state.pop("auth", None)
    return None


def account_sidebar(user):
    """Quién está dentro y el botón de salir, arriba de la barra lateral."""
    with st.sidebar:
        st.markdown(f'<div class="cuenta"><span>{AUTH_TEXT["signed_in_as"]}</span> <b>{_esc(user["name"])}</b>'
                    f'<br><small>{_esc(user["email"])} · {ROLE_LABEL.get(user["role"], user["role"])}</small></div>',
                    unsafe_allow_html=True)
        if st.button(AUTH_TEXT["logout"], key="logout"):
            sign_out()
        st.divider()


def require_admin(user):
    if user is None or user["role"] != "admin":
        st.error(AUTH_TEXT["SelfChange"] if user else AUTH_TEXT["InvalidCredentials"])
        st.stop()


def error_text(e):
    """Mensaje para el usuario a partir de la clase del error (y su detalle en WeakPassword / AccountLocked)."""
    if isinstance(e, auth.WeakPassword):
        return AUTH_TEXT.get(str(e), AUTH_TEXT["WeakPassword"])
    return AUTH_TEXT[type(e).__name__].format(minutes=getattr(e, "minutes", 0))


def client_ip():
    """IP real del visitante: detrás de Caddy viene en X-Forwarded-For; en local, la del socket."""
    forwarded = _header("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else st.context.ip_address
    return ip if isinstance(ip, str) and ip else None


# --- privado ---------------------------------------------------------------------------------------
def _raw_cookie():
    """Valor de la cookie de sesión o None. Solo acepta texto: fuera de un navegador (pruebas) no hay cookies."""
    raw = st.context.cookies.get(COOKIE)
    return raw if isinstance(raw, str) and raw else None


def _user_agent():
    return _header("User-Agent")


def _header(name):
    """Cabecera de la petición como texto, o None (fuera de un navegador las cabeceras no existen)."""
    value = st.context.headers.get(name)
    return value if isinstance(value, str) and value else None


def _with_conn(fn):
    """Abre y cierra una conexión por operación (autocommit). Si Postgres no responde, lo dice y detiene la página."""
    try:
        conn = auth.connect()
    except psycopg.OperationalError:
        st.error(AUTH_TEXT["pg_unavailable"])
        st.stop()
    try:
        return fn(conn)
    finally:
        conn.close()


def _set_cookie_and_reload(raw):
    secure = "; Secure" if config.BASE_URL.startswith("https") else ""
    _js(f'w.document.cookie = "{COOKIE}={raw}; Path=/; Max-Age={SESSION_TTL_DAYS * 86400}; SameSite=Lax{secure}";')


def _clear_cookie_and_reload():
    _js(f'w.document.cookie = "{COOKIE}=; Path=/; Max-Age=0; SameSite=Lax";')


def _js(code):
    """Ejecuta `code` con acceso a la ventana principal (`w`) y después la recarga en la raíz.

    El iframe de `st.iframe` es del mismo origen pero su `sandbox` no trae `allow-top-navigation`, así que navegar desde
    él lo bloquea el navegador. Por eso la recarga no se hace aquí: se inyecta un `<script>` en el documento principal, que
    corre en el contexto de la ventana de arriba y sí puede navegar. Debajo queda un enlace por si algún navegador lo
    impide."""
    reload = "location.replace('/');"
    st.iframe(
        "<script>(function() {"
        f"  const w = window.parent; {code}"
        f"  const s = w.document.createElement('script'); s.textContent = {reload!r}; w.document.body.appendChild(s);"
        "})();</script>",
        height=1,
    )
    st.markdown(f'<p class="nota"><a href="/" target="_self">{AUTH_TEXT["continue"]}</a></p>', unsafe_allow_html=True)
    st.stop()


def _esc(s):
    import html
    return html.escape(str(s))


# --- acciones de administración (views/usuarios.py) -------------------------------------------------
def invite(actor_id, email, name, role):
    """Crea la cuenta y manda la invitación. Devuelve {"error", "link", "mail_error"}: `link` se rellena en modo
    consola (para copiarlo a mano) o cuando el correo falló; `mail_error` si el correo no salió pero la cuenta quedó."""
    return _admin_action(lambda conn: auth.invite(conn, actor_id, email, name, role)[1])


def manage(actor_id, user_id, action, params):
    """deactivate | activate | set_role | resend sobre una cuenta. Mismo resultado que `invite`."""
    fn = {"deactivate": lambda conn: auth.deactivate(conn, actor_id, user_id),
          "activate": lambda conn: auth.activate(conn, actor_id, user_id),
          "set_role": lambda conn: auth.set_role(conn, actor_id, user_id, params["role"]),
          "resend": lambda conn: auth.resend(conn, actor_id, user_id)}[action]
    return _admin_action(fn)


def _admin_action(fn):
    out = {"error": None, "link": None, "mail_error": None}
    try:
        link = _with_conn(fn)
        if link and config.MAIL_BACKEND == "console":
            out["link"] = link
    except auth.MailFailed as e:
        out["link"], out["mail_error"] = e.link, str(e.cause)
    except auth.AuthError as e:
        out["error"] = error_text(e)
    return out
