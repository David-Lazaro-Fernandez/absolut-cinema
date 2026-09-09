# Tareas del proyecto. Cada target es el mismo comando que lanzan launchd (Mac) y los timers de systemd
# (servidor), así se puede correr cualquiera a mano. El scraper usa /usr/bin/python3 (solo stdlib);
# el dashboard usa el venv. Ver project.md > "Programación de tareas".
PY ?= /usr/bin/python3
VENV ?= .venv/bin

.PHONY: help tick snapshot seats occupancy post-start daily health prices concessions delivery capacity capacity-cinemex \
        calibrate-cinemex dashboard backup launchd-load launchd-unload pg-up pg-schema pg-psql pg-admin pg-down sync

help:               ## lista los targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

tick: snapshot seats   ## atajo manual: una captura de cartelera y los dos pases de planos

snapshot:           ## captura de cartelera de ambas cadenas (programada a las 07:30, 13:30 y 20:30)
	$(PY) -m scraper.run

seats: post-start   ## lo que corre cada hora: planos post-inicio (asistencia final)

occupancy:          ## planos de Cinépolis a ~60 min de empezar (preventa; solo a mano)
	$(PY) -m scraper.sample --occupancy

post-start:         ## planos de Cinépolis 15–75 min después de empezar (asistencia final)
	$(PY) -m scraper.sample --post-start

daily: health prices concessions   ## lo que corre una vez al día a las 06:00 (usar con -k)

health:             ## reporte de salud de la captura (sale con 1 si hay problemas)
	$(PY) -m scraper.health

prices:             ## precios: una función por cine, formato y tipo de día (7 días)
	$(PY) -m scraper.sample --prices

concessions:        ## menú de dulcería de Cinépolis con precio por complejo (se renueva cada 7 días)
	$(PY) -m scraper.sample --concessions

delivery:           ## dulcería a domicilio en Rappi y DiDi Food, a las 15:00 con las tiendas abiertas (renovadas cada 7 días)
	$(PY) -m scraper.delivery

capacity:           ## aforo por sala de Cinépolis; con REFRESH=1 vuelve a medir las conocidas
	$(PY) -m scraper.sample --capacity $(if $(REFRESH),--refresh,)

capacity-cinemex:   ## aforo de Cinemex (abre órdenes de checkout; lanzar a mano)
	$(PY) -m scraper.sample --capacity --chain cinemex $(if $(REFRESH),--refresh,)

calibrate-cinemex:  ## calibración del semáforo de Cinemex, 100 funciones por nivel (checkout; a mano o timer opcional)
	$(PY) -m scraper.sample --occupancy --chain cinemex --per-level $(or $(PER_LEVEL),100) --lead 60 --tolerance 45 --limit $(or $(LIMIT),60)

pg-up:              ## Postgres 16 local en Docker para probar el esquema histórico (puerto 5433)
	docker compose -f deploy/docker-compose.dev.yml up -d --wait

pg-schema:          ## aplica deploy/postgres/schema.sql al Postgres local
	docker compose -f deploy/docker-compose.dev.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U absolut -d absolut_cinema < deploy/postgres/schema.sql

pg-admin:           ## pgAdmin en el navegador (http://localhost:5050, contraseña de la base: absolut-dev)
	docker compose -f deploy/docker-compose.dev.yml --profile admin up -d --wait pgadmin
	open http://localhost:5050

pg-psql:            ## consola psql en el Postgres local
	docker compose -f deploy/docker-compose.dev.yml exec postgres psql -U absolut -d absolut_cinema

pg-down:            ## apaga Postgres y pgAdmin locales y borra sus datos
	docker compose -f deploy/docker-compose.dev.yml --profile admin down -v

sync:               ## copia lo nuevo de SQLite al archivo histórico en Postgres (programado a :22 y :52)
	$(VENV)/python -m sync.run

dashboard:          ## Streamlit local
	$(VENV)/streamlit run app.py

backup:             ## respaldo (requiere BACKUP_BUCKET en el entorno)
	bash deploy/backup.sh

launchd-load:       ## Mac: cargar los cinco agentes (cartelera 3/día, planos cada hora, diario, delivery, sync)
	for a in scraper seats daily delivery sync; do launchctl bootstrap gui/$$(id -u) scraper/com.absolut-cinema.$$a.plist; done

launchd-unload:     ## Mac: descargar los agentes (antes de mover el scraper al servidor)
	-for a in scraper seats daily delivery sync; do launchctl bootout gui/$$(id -u)/com.absolut-cinema.$$a; done
