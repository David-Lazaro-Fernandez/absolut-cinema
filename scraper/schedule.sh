#!/bin/zsh
# Lanzado por launchd cada 15 min (ver scraper/com.absolut-cinema.scraper.plist).
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/logs
exec /usr/bin/python3 -m scraper.run >> data/logs/launchd.out 2>&1
