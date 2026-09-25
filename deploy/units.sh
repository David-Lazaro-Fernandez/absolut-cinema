#!/usr/bin/env bash
# Deja /etc/systemd/system igual que el repo: enlaza las unidades generadas desde jobs/registry.py (deploy/systemd/) y el
# dashboard, apaga y quita las de absolut-cinema que ya no existen en el repo (una llave renombrada o borrada) y enciende
# los timers que el registro marca como encendidos. Idempotente. Lo llaman install.sh y update.sh, como root.
set -euo pipefail

APP="${APP:-/opt/absolut-cinema}"
SYSTEMD=/etc/systemd/system
cd "$APP"

for link in "$SYSTEMD"/absolut-cinema-*.service "$SYSTEMD"/absolut-cinema-*.timer; do
  [ -L "$link" ] || continue
  [ -e "$link" ] && continue
  name="$(basename "$link")"
  echo ">> quitando $name (ya no está en el repo)"
  # Sin el archivo de la unidad `disable` puede no encontrarla: se detiene la que sigue cargada y se borran a mano sus
  # enlaces en *.wants.
  systemctl stop "$name" 2>/dev/null || true
  rm -f "$link" "$SYSTEMD"/*.wants/"$name"
done

for unit in deploy/systemd/*.service deploy/systemd/*.timer deploy/absolut-cinema-dashboard.service; do
  ln -sf "$APP/$unit" "$SYSTEMD/$(basename "$unit")"
done
systemctl daemon-reload

mapfile -t timers < <(/usr/bin/python3 -m jobs.units timers)
systemctl enable --now "${timers[@]}"
