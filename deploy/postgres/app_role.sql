-- Rol de Postgres del dashboard: escribe solo en el esquema `app` y lee el archivo histórico (`public`).
-- Aplicar después de schema.sql y auth.sql, como propietario de la base, pasando la contraseña como variable de psql:
--   psql "$AC_PG_DSN" -v ON_ERROR_STOP=1 -v app_password='…' -f deploy/postgres/app_role.sql
-- Idempotente: si el rol ya existe solo refresca los permisos. El DSN resultante va en AC_AUTH_PG_DSN.
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'absolut_app') AS role_missing \gset
\if :role_missing
  CREATE ROLE absolut_app LOGIN PASSWORD :'app_password';
\endif

GRANT USAGE ON SCHEMA app TO absolut_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO absolut_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO absolut_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO absolut_app;

GRANT USAGE ON SCHEMA public TO absolut_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO absolut_app;
-- Las particiones mensuales que el sync crea después también deben poder leerse.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO absolut_app;
