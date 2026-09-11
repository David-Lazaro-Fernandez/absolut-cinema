"""Cuentas, sesiones y enlaces de acceso del dashboard, sobre el esquema `app` de PostgreSQL.

Corre en el venv (psycopg). Es la única capa que escribe en Postgres desde el dashboard y solo toca `app.*`; el
archivo histórico (`public`) sigue siendo del sync. No importa Streamlit: el pegamento con la cookie y las páginas
vive en `ui/auth.py`. Las reglas puras (hash de contraseña, tokens, bloqueo) están en `auth.security` y se prueban
sin base de datos; los flujos que usan vistas y línea de comandos, en `auth.flows`.
"""
from .db import connect, rows
from .errors import (
                     AccountInactive,
                     AccountLocked,
                     AuthError,
                     DuplicateEmail,
                     InvalidCredentials,
                     LastAdmin,
                     MailFailed,
                     SelfChange,
                     TokenInvalid,
                     WeakPassword,
)
from .flows import (
                     activate,
                     deactivate,
                     invite,
                     link_for,
                     login,
                     logout,
                     peek_token,
                     redeem_token,
                     request_reset,
                     resend,
                     set_role,
)
from .sessions import current_session, prune
from .users import list_users

__all__ = [
    "AccountInactive", "AccountLocked", "AuthError", "DuplicateEmail", "InvalidCredentials", "LastAdmin", "MailFailed",
    "SelfChange",
    "TokenInvalid", "WeakPassword",
    "activate", "connect", "current_session", "deactivate", "invite", "link_for", "list_users", "login", "logout",
    "peek_token", "prune", "redeem_token", "request_reset", "resend", "rows", "set_role",
]
