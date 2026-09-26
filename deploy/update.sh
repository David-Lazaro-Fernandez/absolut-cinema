#!/usr/bin/env bash
# Despliegue continuo: trae el último commit estable (rama `stable`, la mueve GitHub Actions solo si pasaron las
# pruebas), reinstala dependencias si cambiaron, recarga unidades si cambió deploy/ y reinicia el dashboard. Corre como
# root desde absolut-cinema-deploy.timer (cada 15 min) o a mano con `make deploy`; con REF=<commit|rama> despliega otro
# punto (p. ej. para volver atrás). No toca data/. Una línea en data/logs/deploy.log solo cuando despliega o falla.
#
# Las capturas en curso no se tocan ni se esperan: cada corrida ya cargó sus módulos al arrancar y la siguiente toma el
# código nuevo.
set -euo pipefail

APP="${APP:-/opt/absolut-cinema}"
REF="${REF:-origin/stable}"
LOG="$APP/data/logs/deploy.log"
cd "$APP"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG"; }

before="$(sudo -u absolut git rev-parse HEAD)"
sudo -u absolut git fetch --quiet --prune origin
target="$(sudo -u absolut git rev-parse "$REF")"

# Cada 15 min casi siempre no hay nada nuevo: se sale en silencio para no llenar deploy.log.
if [ "$before" = "$target" ]; then
  exit 0
fi

changed="$(sudo -u absolut git diff --name-only "$before" "$target")"
sudo -u absolut git reset --hard --quiet "$target"

if grep -q '^requirements-' <<< "$changed"; then
  log "cambiaron requirements: reinstalando el venv"
  sudo -u absolut .venv/bin/pip install -q -r requirements-dashboard.txt
fi
if grep -Eq '^deploy/.*\.(service|timer)$' <<< "$changed"; then
  log "cambiaron unidades de systemd: enlazando, quitando las que ya no existen y encendiendo timers"
  bash deploy/units.sh
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
