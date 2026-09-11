#!/usr/bin/env bash
# Despliegue diario: trae el último commit estable (rama `stable`, la mueve GitHub Actions solo si pasaron las pruebas),
# reinstala dependencias si cambiaron, recarga unidades si cambió deploy/ y reinicia el dashboard. Corre como root
# desde absolut-cinema-deploy.timer (07:07) o a mano con `make deploy`; con REF=<commit|rama> despliega otro punto
# (p. ej. para volver atrás). No toca data/ ni Postgres. Una línea por corrida en data/logs/deploy.log.
set -euo pipefail

APP="${APP:-/opt/absolut-cinema}"
REF="${REF:-origin/stable}"
LOG="$APP/data/logs/deploy.log"
cd "$APP"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG"; }

before="$(sudo -u absolut git rev-parse HEAD)"
sudo -u absolut git fetch --quiet --prune origin
target="$(sudo -u absolut git rev-parse "$REF")"

if [ "$before" = "$target" ]; then
  log "sin cambios: ya está en ${target:0:10} ($REF)"
  exit 0
fi

changed="$(sudo -u absolut git diff --name-only "$before" "$target")"
sudo -u absolut git reset --hard --quiet "$target"

if grep -q '^requirements-' <<< "$changed"; then
  log "cambiaron requirements: reinstalando el venv"
  sudo -u absolut .venv/bin/pip install -q -r requirements-dashboard.txt -r requirements-sync.txt
fi
if grep -Eq '^deploy/.*\.(service|timer)$' <<< "$changed"; then
  log "cambiaron unidades de systemd: daemon-reload"
  systemctl daemon-reload
fi

systemctl restart absolut-cinema-dashboard
for _ in $(seq 1 20); do
  if curl -fs http://127.0.0.1:8501/_stcore/health >/dev/null; then
    log "desplegado ${before:0:10} -> ${target:0:10}: dashboard sano"
    exit 0
  fi
  sleep 1
done
log "ERROR: ${target:0:10} desplegado pero el dashboard no responde; revisa journalctl -u absolut-cinema-dashboard"
exit 1
