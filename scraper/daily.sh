#!/bin/zsh
# Lanzado por launchd una vez al día a las 06:00 (ver scraper/com.absolut-cinema.daily.plist). Equivale a `make daily`.
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/logs
/usr/bin/python3 -m scraper.health >> data/logs/launchd.out 2>&1
exec /usr/bin/python3 -m scraper.sample --prices >> data/logs/launchd.out 2>&1
