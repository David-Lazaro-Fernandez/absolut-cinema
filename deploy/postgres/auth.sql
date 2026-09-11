-- Esquema `app`: cuentas, sesiones, tokens y auditoría del acceso al dashboard. Copia ejecutable del DDL de
-- docs/postgres-esquema.md § "Esquema app": si cambia uno, cambia el otro. Aplicar con `make auth-schema` (local) o
-- `psql -f` contra RDS como propietario de la base. El rol del dashboard y sus permisos van en app_role.sql.
-- Es la única parte de Postgres que escribe el dashboard (auth/); el archivo histórico (public) sigue siendo del sync.
BEGIN;

CREATE SCHEMA IF NOT EXISTS app;

CREATE TYPE app.role_t AS ENUM ('admin', 'viewer');

CREATE TABLE app.account (                        -- `account` y no `user`: palabra reservada
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email           text NOT NULL,
  name            text NOT NULL,
  role            app.role_t NOT NULL DEFAULT 'viewer',
  password_hash   text,                           -- NULL hasta que acepte la invitación (auth.security.hash_password)
  active          boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      bigint REFERENCES app.account,  -- NULL: creada desde la línea de comandos
  last_login_at   timestamptz,
  failed_logins   smallint NOT NULL DEFAULT 0,    -- intentos fallidos seguidos; se reinicia al entrar
  last_failed_at  timestamptz,
  locked_until    timestamptz                     -- bloqueo temporal tras demasiados fallos
);
CREATE UNIQUE INDEX account_email_key ON app.account (lower(email));

CREATE TABLE app.session (                        -- una fila por cookie emitida; solo se guarda el hash del token
  token_hash    text PRIMARY KEY,                 -- sha256 hex del valor de la cookie
  account_id    bigint NOT NULL REFERENCES app.account,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,             -- deslizante: se extiende con el uso
  revoked_at    timestamptz,                      -- cierre de sesión, cambio de contraseña o desactivación
  ip            inet,
  user_agent    text
);
CREATE INDEX ON app.session (account_id);
CREATE INDEX ON app.session (expires_at);

CREATE TABLE app.token (                          -- enlaces de invitación y de restablecimiento: un solo uso
  token_hash  text PRIMARY KEY,
  account_id  bigint NOT NULL REFERENCES app.account,
  purpose     text NOT NULL CHECK (purpose IN ('invite', 'reset')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_by  bigint REFERENCES app.account       -- NULL: lo pidió el propio usuario desde "olvidé mi contraseña"
);
CREATE INDEX ON app.token (account_id, purpose, created_at);

CREATE TABLE app.audit (                          -- quién hizo qué: altas, cambios de rol, accesos y cierres
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at         timestamptz NOT NULL DEFAULT now(),
  actor_id   bigint REFERENCES app.account,       -- NULL: la línea de comandos o el propio flujo público
  action     text NOT NULL,                       -- create, invite, resend, activate, deactivate, set_role,
                                                  -- set_password, reset_requested, login_ok, login_failed, logout
  target_id  bigint REFERENCES app.account,
  detail     jsonb
);
CREATE INDEX ON app.audit (at);

COMMIT;
