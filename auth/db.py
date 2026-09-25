"""Base de cuentas del dashboard: SQLite en `config.APP_DB_PATH` (`data/app.db`), separada de `snapshots.db`.

`snapshots.db` la escribe solo la captura y el dashboard la abre en solo lectura; `app.db` la escribe solo `auth/`
(desde el dashboard y desde `auth.cli`). El esquema se crea al conectar (`CREATE TABLE IF NOT EXISTS`, aditivo, como
`scraper/store.py`). Varias sesiones de Streamlit escriben a la vez: WAL y `busy_timeout` las serializan.

Las fechas se guardan como texto ISO en UTC con microsegundos fijos, así las comparaciones de SQL entre textos son
cronológicas; al leer, las columnas `*_at` y `locked_until` vuelven como `datetime` y las banderas como `bool`.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from scraper import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (              -- `account` y no `user`: el nombre que ya usa el resto de auth/
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  email           TEXT NOT NULL,
  name            TEXT NOT NULL,
  role            TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'viewer')),
  password_hash   TEXT,                           -- NULL hasta que acepte la invitación (auth.security.hash_password)
  active          INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL,
  created_by      INTEGER REFERENCES account,     -- NULL: creada desde la línea de comandos
  last_login_at   TEXT,
  failed_logins   INTEGER NOT NULL DEFAULT 0,     -- intentos fallidos seguidos; se reinicia al entrar
  last_failed_at  TEXT,
  locked_until    TEXT                            -- bloqueo temporal tras demasiados fallos
);
CREATE UNIQUE INDEX IF NOT EXISTS account_email_key ON account (lower(email));

CREATE TABLE IF NOT EXISTS session (              -- una fila por cookie emitida; solo se guarda el hash del token
  token_hash    TEXT PRIMARY KEY,                 -- sha256 hex del valor de la cookie
  account_id    INTEGER NOT NULL REFERENCES account,
  created_at    TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL,
  expires_at    TEXT NOT NULL,                    -- deslizante: se extiende con el uso
  revoked_at    TEXT,                             -- cierre de sesión, cambio de contraseña o desactivación
  ip            TEXT,
  user_agent    TEXT
);
CREATE INDEX IF NOT EXISTS session_account ON session (account_id);
CREATE INDEX IF NOT EXISTS session_expires ON session (expires_at);

CREATE TABLE IF NOT EXISTS token (                -- enlaces de invitación y de restablecimiento: un solo uso
  token_hash  TEXT PRIMARY KEY,
  account_id  INTEGER NOT NULL REFERENCES account,
  purpose     TEXT NOT NULL CHECK (purpose IN ('invite', 'reset')),
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  used_at     TEXT,
  created_by  INTEGER REFERENCES account          -- NULL: lo pidió el propio usuario desde "olvidé mi contraseña"
);
CREATE INDEX IF NOT EXISTS token_account ON token (account_id, purpose, created_at);

CREATE TABLE IF NOT EXISTS audit (                -- quién hizo qué: altas, cambios de rol, accesos y cierres
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  actor_id   INTEGER REFERENCES account,          -- NULL: la línea de comandos o el propio flujo público
  action     TEXT NOT NULL,                       -- create, invite, resend, activate, deactivate, set_role, …
  target_id  INTEGER REFERENCES account,
  detail     TEXT                                 -- JSON
);
CREATE INDEX IF NOT EXISTS audit_at ON audit (at);
"""

_BOOLEANS = {"active", "has_password", "pending_invite"}


def iso(when):
    """Instante como texto ISO en UTC con microsegundos: el formato con el que se guardan y comparan las fechas."""
    return when.astimezone(timezone.utc).isoformat(timespec="microseconds")


sqlite3.register_adapter(datetime, iso)


def _row(cursor, values):
    out = {}
    for (name, *_), value in zip(cursor.description, values):
        if isinstance(value, str) and (name.endswith("_at") or name == "locked_until"):
            value = datetime.fromisoformat(value)
        elif name in _BOOLEANS and value is not None:
            value = bool(value)
        out[name] = value
    return out


def connect(path=None):
    """Conexión en autocommit (cada sentencia suelta se confirma sola); `transaction(conn)` agrupa las escrituras de
    un flujo. Crea el archivo y el esquema si no existen."""
    db = path or config.APP_DB_PATH
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = _row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn):
    """Agrupa escrituras en una transacción que toma el candado de escritura al empezar (`BEGIN IMMEDIATE`), para
    que dos sesiones que entran a la vez no choquen a la mitad. Confirma al salir o deshace si hubo excepción."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@contextmanager
def cursor(conn):
    """Cursor para varias sentencias seguidas (`cur.fetchone()`, `cur.rowcount`), con la forma `with … as cur`."""
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def rows(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()
