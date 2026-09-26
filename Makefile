# Tareas del proyecto. Lo programado vive en jobs/registry.py: cada timer de systemd (servidor) y agente de launchd (Mac)
# ejecuta `make job KEY=llave`, y los targets de un solo trabajo (snapshot, seats, health…) son atajos de lo mismo, así
# se puede correr cualquiera a mano igual que en automático. El scraper usa /usr/bin/python3 (solo stdlib); el dashboard
# usa el venv. Ver ARCHITECTURE.md > "Programación".
PY ?= /usr/bin/python3
VENV ?= .venv/bin

.PHONY: help job units units-check tick snapshot seats occupancy post-start health prices concessions delivery capacity capacity-cinemex presale \
        calibrate-cinemex dashboard backup launchd-load launchd-unload \
        user-create user-list user-reset user-deactivate user-activate auth-prune deploy check lint test test-live fixtures hooks \
        marketing-dev marketing-build

help:               ## lista los targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

job:                ## corre un trabajo del registro como lo hace su timer: KEY=snapshot|seats|prices|… (jobs/keys.py)
	$(PY) -m jobs.run $(KEY)

units:              ## regenera deploy/systemd/ y la tabla de ARCHITECTURE.md desde jobs/registry.py
	$(PY) -m jobs.units write

units-check:        ## sale con 1 si deploy/systemd/ o ARCHITECTURE.md no coinciden con el registro
	$(PY) -m jobs.units check

tick: snapshot seats   ## atajo manual: una captura de cartelera y el pase de planos

snapshot:           ## captura de cartelera de ambas cadenas (trabajo `snapshot`)
	$(PY) -m jobs.run snapshot

seats:              ## planos post-inicio, asistencia final (trabajo `seats`, cada hora)
	$(PY) -m jobs.run seats

occupancy:          ## planos de Cinépolis a ~60 min de empezar (preventa; solo a mano)
	$(PY) -m scraper.sample --occupancy

post-start:         ## planos de Cinépolis 15–75 min después de empezar (asistencia final)
	$(PY) -m scraper.sample --post-start

health:             ## reporte de salud de la captura, sale con 1 si hay problemas (trabajo `health`)
	$(PY) -m jobs.run health

prices:             ## precios: una función por cine, formato y tipo de día (7 días); el trabajo `prices` añade concessions
	$(PY) -m scraper.sample --prices

concessions:        ## menú de dulcería de Cinépolis con precio por complejo (se renueva cada 7 días)
	$(PY) -m scraper.sample --concessions

delivery:           ## dulcería a domicilio en Rappi y DiDi Food, tiendas renovadas cada 7 días (trabajo `delivery`)
	$(PY) -m jobs.run delivery

presale:            ## preventas de ambas cadenas: títulos en preventa y butacas vendidas de su panel (trabajo `presale`)
	$(PY) -m jobs.run presale

capacity:           ## aforo por sala de Cinépolis en AC_SEATS_PLAZAS; REFRESH=1 vuelve a medir; PLAZAS=all (o gdl,mty) cambia el alcance
	$(PY) -m scraper.sample --capacity $(if $(REFRESH),--refresh,) $(if $(PLAZAS),--plazas $(PLAZAS),) $(if $(WORKERS),--workers $(WORKERS),)

capacity-cinemex:   ## aforo de Cinemex con el plano público; PLAZAS=all para la pasada nacional única
	$(PY) -m scraper.sample --capacity --chain cinemex $(if $(REFRESH),--refresh,) $(if $(PLAZAS),--plazas $(PLAZAS),) $(if $(WORKERS),--workers $(WORKERS),)

calibrate-cinemex:  ## calibración del semáforo de Cinemex, 100 funciones por nivel (trabajo `calibrate-cinemex`)
	$(PY) -m scraper.sample --occupancy --chain cinemex --per-level $(or $(PER_LEVEL),100) --lead 60 --tolerance 45 --limit $(or $(LIMIT),60)

dashboard:          ## Streamlit local
	$(VENV)/streamlit run app.py

marketing-dev:      ## landing page pública en local (Next.js, marketing/); requiere `npm install` una vez ahí
	cd marketing && npm run dev

marketing-build:    ## exporta la landing page pública como sitio estático a marketing/out
	cd marketing && npm run build

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

auth-prune:         ## borra sesiones y enlaces vencidos hace más de 90 días (trabajo `auth-prune`)
	$(PY) -m jobs.run auth-prune

backup:             ## respaldo, requiere BACKUP_BUCKET en el entorno (trabajo `backup`)
	$(PY) -m jobs.run backup

deploy:             ## servidor: trae origin/stable (o REF=…), reinstala si cambió requirements y reinicia el dashboard (trabajo `deploy`)
	$(PY) -m jobs.run deploy

check: lint test    ## lo que corre el pre-push y CI: lint, imports sin dependencias y pruebas

lint:               ## ruff (pyproject.toml) y comprobación de que scraper/ y analytics/ importan con el Python del sistema
	$(VENV)/ruff check .
	$(PY) -m compileall -q scraper analytics jobs
	$(PY) -c "import analytics, scraper.run, scraper.sample, scraper.health, scraper.delivery, jobs.run, jobs.units"

test:               ## pruebas (las de pantalla se omiten si no hay data/snapshots.db); la captura corre contra respuestas grabadas
	$(VENV)/python -m pytest -q tests/

test-live:          ## la captura contra las APIs reales, alcance chico de cada cadena (red; Cinépolis necesita WARP fuera de la Mac)
	AC_LIVE=1 $(VENV)/python -m pytest -q tests/test_live_capture.py

fixtures:           ## graba de nuevo las respuestas reales de ambas APIs y el esperado; EXPECTED=1 solo regenera el esperado
	$(PY) scripts/capture_fixtures.py $(if $(EXPECTED),--expected,)

hooks:              ## activa los hooks de git del repo (.githooks: pre-push corre make check); una vez por clon
	git config core.hooksPath .githooks
	@echo "pre-push activo; para saltarlo en una emergencia: git push --no-verify"

launchd-load:       ## Mac: genera en data/launchd los agentes del registro con host mac y los carga
	$(PY) -m jobs.units launchd data/launchd
	for p in data/launchd/com.absolut-cinema.*.plist; do launchctl bootstrap gui/$$(id -u) "$$p"; done

# `scraper` y `daily` son las etiquetas de antes del registro (hasta el 2026-09-25); se descargan por si siguen cargadas.
launchd-unload:     ## Mac: descarga los agentes (antes de mover el scraper al servidor)
	-for a in snapshot seats prices health delivery sync scraper daily; do launchctl bootout gui/$$(id -u)/com.absolut-cinema.$$a; done
