#!/usr/bin/env bash
# Respaldo diario: copias consistentes de snapshots.db y app.db (cuentas) + sync del crudo al bucket.
# Requiere `aws` (awscli) y credenciales en ~/.aws/credentials del usuario que corre esto.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f /etc/absolut-cinema.env ] && set -a && . /etc/absolut-cinema.env && set +a
: "${BACKUP_BUCKET:?Define BACKUP_BUCKET en /etc/absolut-cinema.env}"
ENDPOINT_ARG=${BACKUP_ENDPOINT:+--endpoint-url "$BACKUP_ENDPOINT"}

mkdir -p data/backups data/logs
stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
db_copy="data/backups/snapshots-$stamp.db"
# .backup usa la API de respaldo en línea: no bloquea al scraper y sale consistente aun con WAL.
sqlite3 data/snapshots.db ".backup '$db_copy'"
gzip -f "$db_copy"

# Cuentas, sesiones y auditoría del dashboard: sin este archivo nadie entra, así que va con la misma copia en línea.
app_copy=""
if [ -f data/app.db ]; then
  app_copy="data/backups/app-$stamp.db"
  sqlite3 data/app.db ".backup '$app_copy'"
  gzip -f "$app_copy"
fi

# shellcheck disable=SC2086
aws $ENDPOINT_ARG s3 cp "$db_copy.gz" "$BACKUP_BUCKET/db/" --only-show-errors
if [ -n "$app_copy" ]; then
  # shellcheck disable=SC2086
  aws $ENDPOINT_ARG s3 cp "$app_copy.gz" "$BACKUP_BUCKET/app/" --only-show-errors
fi
# shellcheck disable=SC2086
aws $ENDPOINT_ARG s3 sync data/raw "$BACKUP_BUCKET/raw/" --only-show-errors
# shellcheck disable=SC2086
aws $ENDPOINT_ARG s3 cp data/logs/run.log "$BACKUP_BUCKET/logs/run-$stamp.log" --only-show-errors

# Conservar 7 copias locales de cada base.
ls -1t data/backups/snapshots-*.db.gz | tail -n +8 | xargs -r rm -f
ls -1t data/backups/app-*.db.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
echo "$(date -u +%FT%TZ) backup ok $db_copy.gz" >> data/logs/backup.log
