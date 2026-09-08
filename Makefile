# Tareas del proyecto. Cada target es el mismo comando que lanzan launchd (Mac) y los timers de systemd
# (servidor), así se puede correr cualquiera a mano. El scraper usa /usr/bin/python3 (solo stdlib);
# el dashboard usa el venv. Ver project.md > "Programación de tareas".
PY ?= /usr/bin/python3
VENV ?= .venv/bin

.PHONY: help tick snapshot occupancy post-start daily health prices capacity capacity-cinemex \
        calibrate-cinemex dashboard backup launchd-load launchd-unload

help:               ## lista los targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

tick: snapshot occupancy post-start   ## lo que corre cada 15 min (snapshot + dos pases de planos)

snapshot:           ## snapshot de cartelera de ambas cadenas
	$(PY) -m scraper.run

occupancy:          ## planos de Cinépolis a ~60 min de empezar (preventa)
	$(PY) -m scraper.sample --occupancy

post-start:         ## planos de Cinépolis 10–30 min después de empezar (asistencia final)
	$(PY) -m scraper.sample --post-start

daily: health prices   ## lo que corre una vez al día

health:             ## reporte de salud de la captura (sale con 1 si hay problemas)
	$(PY) -m scraper.health

prices:             ## precios: una función por cine, formato y tipo de día (7 días)
	$(PY) -m scraper.sample --prices

capacity:           ## aforo por sala de Cinépolis; con REFRESH=1 vuelve a medir las conocidas
	$(PY) -m scraper.sample --capacity $(if $(REFRESH),--refresh,)

capacity-cinemex:   ## aforo de Cinemex (abre órdenes de checkout; lanzar a mano)
	$(PY) -m scraper.sample --capacity --chain cinemex $(if $(REFRESH),--refresh,)

calibrate-cinemex:  ## calibración del semáforo de Cinemex, 100 funciones por nivel (checkout; a mano o timer opcional)
	$(PY) -m scraper.sample --occupancy --chain cinemex --per-level $(or $(PER_LEVEL),100) --lead 60 --tolerance 45 --limit $(or $(LIMIT),60)

dashboard:          ## Streamlit local
	$(VENV)/streamlit run app.py

backup:             ## respaldo (requiere BACKUP_BUCKET en el entorno)
	bash deploy/backup.sh

launchd-load:       ## Mac: cargar los dos agentes (cada 15 min y diario)
	launchctl bootstrap gui/$$(id -u) scraper/com.absolut-cinema.scraper.plist
	launchctl bootstrap gui/$$(id -u) scraper/com.absolut-cinema.daily.plist

launchd-unload:     ## Mac: descargar los agentes (antes de mover el scraper al servidor)
	-launchctl bootout gui/$$(id -u)/com.absolut-cinema.scraper
	-launchctl bootout gui/$$(id -u)/com.absolut-cinema.daily
