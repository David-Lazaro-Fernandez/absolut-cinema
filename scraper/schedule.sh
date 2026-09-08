#!/bin/zsh
# Lanzado por launchd cada 15 min (ver scraper/com.absolut-cinema.scraper.plist). Equivale a `make tick`.
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/logs
/usr/bin/python3 -m scraper.run >> data/logs/launchd.out 2>&1
# Ocupación de Cinépolis: planos de las funciones que empiezan en ~60 min (preventa)…
/usr/bin/python3 -m scraper.sample --occupancy >> data/logs/launchd.out 2>&1
# …y de las que empezaron hace 10–30 min (asistencia final, target del modelo de consumo).
exec /usr/bin/python3 -m scraper.sample --post-start >> data/logs/launchd.out 2>&1
