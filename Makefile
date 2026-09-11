# Tareas del proyecto. Cada target es el mismo comando que lanzan launchd (Mac) y los timers de systemd
# (servidor), así se puede correr cualquiera a mano. El scraper usa /usr/bin/python3 (solo stdlib);
# el dashboard usa el venv. Ver project.md > "Programación de tareas".
PY ?= /usr/bin/python3
VENV ?= .venv/bin

.PHONY: help tick snapshot seats occupancy post-start daily health prices concessions delivery capacity capacity-cinemex \
        calibrate-cinemex dashboard backup launchd-load launchd-unload pg-up pg-schema pg-psql pg-admin pg-down sync \
        auth-schema user-create user-list user-reset user-deactivate user-activate auth-prune deploy check lint test hooks

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

auth-schema:        ## esquema `app` (cuentas y sesiones) y rol absolut_app en el Postgres local; APP_PASSWORD opcional
	docker compose -f deploy/docker-compose.dev.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U absolut -d absolut_cinema < deploy/postgres/auth.sql
	docker compose -f deploy/docker-compose.dev.yml exec -T postgres psql -v ON_ERROR_STOP=1 -v app_password="$(or $(APP_PASSWORD),absolut-dev)" -U absolut -d absolut_cinema < deploy/postgres/app_role.sql

user-create:        ## cuenta nueva con enlace de invitación: EMAIL= NAME= [ROLE=admin|viewer] [NOMAIL=1]
	$(VENV)/python -m auth.cli create --email "$(EMAIL)" --name "$(NAME)" --role $(or $(ROLE),viewer) $(if $(NOMAIL),--no-mail,)

user-list:          ## todas las cuentas del dashboard
	$(VENV)/python -m auth.cli list

user-reset:         ## enlace nuevo de invitación o restablecimiento: EMAIL= [NOMAIL=1]
	$(VENV)/python -m auth.cli reset --email "$(EMAIL)" $(if $(NOMAIL),--no-mail,)

user-deactivate:    ## desactiva una cuenta y cierra sus sesiones: EMAIL=
	$(VENV)/python -m auth.cli deactivate --email "$(EMAIL)"

user-activate:      ## reactiva una cuenta: EMAIL=
	$(VENV)/python -m auth.cli activate --email "$(EMAIL)"

auth-prune:         ## borra sesiones y enlaces vencidos hace más de 90 días (programado los domingos 04:07)
	$(VENV)/python -m auth.cli prune

backup:             ## respaldo (requiere BACKUP_BUCKET en el entorno)
	bash deploy/backup.sh

deploy:             ## servidor: trae origin/stable (o REF=…), reinstala si cambió requirements y reinicia el dashboard (07:07)
	bash deploy/update.sh

check: lint test    ## lo que corre el pre-push y CI: lint, imports sin dependencias y pruebas

lint:               ## ruff (pyproject.toml) y comprobación de que scraper/ y analytics/ importan con el Python del sistema
	$(VENV)/ruff check .
	$(PY) -m compileall -q scraper analytics
	$(PY) -c "import analytics, scraper.run, scraper.sample, scraper.health, scraper.delivery"

test:               ## pruebas (las de pantalla se omiten si no hay data/snapshots.db o el Postgres de desarrollo)
	$(VENV)/python -m pytest -q tests/

hooks:              ## activa los hooks de git del repo (.githooks: pre-push corre make check); una vez por clon
	git config core.hooksPath .githooks
	@echo "pre-push activo; para saltarlo en una emergencia: git push --no-verify"

launchd-load:       ## Mac: cargar los cinco agentes (cartelera 3/día, planos cada hora, diario, delivery, sync)
	for a in scraper seats daily delivery sync; do launchctl bootstrap gui/$$(id -u) scraper/com.absolut-cinema.$$a.plist; done

launchd-unload:     ## Mac: descargar los agentes (antes de mover el scraper al servidor)
	-for a in scraper seats daily delivery sync; do launchctl bootout gui/$$(id -u)/com.absolut-cinema.$$a; done
