#!/usr/bin/env bash
# Instalación idempotente en Ubuntu 24.04 (droplet de DigitalOcean o EC2). Correr como root:
#   git clone <repo> /opt/absolut-cinema && bash /opt/absolut-cinema/deploy/install.sh
set -euo pipefail
APP=/opt/absolut-cinema
cd "$APP"

timedatectl set-timezone America/Mexico_City
apt-get update -qq
apt-get install -y -qq python3 python3-venv sqlite3 awscli debian-keyring debian-archive-keyring apt-transport-https curl

if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy
fi

id -u absolut >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin absolut
mkdir -p data/logs data/raw data/backups
chown -R absolut:absolut "$APP"

[ -f /etc/absolut-cinema.env ] || { cp deploy/absolut-cinema.env.example /etc/absolut-cinema.env; chmod 600 /etc/absolut-cinema.env; }

sudo -u absolut python3 -m venv .venv
sudo -u absolut .venv/bin/pip install -q -r requirements-dashboard.txt

for unit in absolut-cinema-scraper.service absolut-cinema-scraper.timer \
            absolut-cinema-dashboard.service absolut-cinema-backup.service absolut-cinema-backup.timer \
            absolut-cinema-prices.service absolut-cinema-prices.timer \
            absolut-cinema-health.service absolut-cinema-health.timer \
            absolut-cinema-capacity.service absolut-cinema-capacity.timer \
            absolut-cinema-calibrate-cinemex.service absolut-cinema-calibrate-cinemex.timer; do
  ln -sf "$APP/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload

# Primer snapshot antes de arrancar el dashboard: la base data/snapshots.db la crea el scraper y el
# dashboard solo la lee. Si ya copiaste data/ desde otra máquina, este paso se salta solo. Tarda 2–5 min.
if [ ! -f data/snapshots.db ]; then
  echo ">> No hay base; corriendo el primer snapshot (2–5 min)…"
  sudo -u absolut /usr/bin/python3 -m scraper.run || echo ">> El primer snapshot falló; el timer lo reintenta en 15 min."
fi

systemctl enable --now absolut-cinema-scraper.timer absolut-cinema-dashboard.service absolut-cinema-backup.timer \
                       absolut-cinema-prices.timer absolut-cinema-health.timer absolut-cinema-capacity.timer
# La calibración de Cinemex abre órdenes de checkout: queda enlazada pero apagada. Encender a mano cuando se decida:
#   systemctl enable --now absolut-cinema-calibrate-cinemex.timer

if [ ! -f /etc/caddy/Caddyfile ] || ! grep -q 8501 /etc/caddy/Caddyfile; then
  cp deploy/Caddyfile /etc/caddy/Caddyfile
  echo ">> Edita /etc/caddy/Caddyfile (dominio y hash de basic_auth) y luego: systemctl reload caddy"
fi

echo ">> Listo. Revisa: systemctl list-timers absolut-cinema-*  |  tail -f $APP/data/logs/run.log"
