
# absolut-cinema

<img width="1194" height="584" alt="Frame 1 (2)" src="https://github.com/user-attachments/assets/526e5100-e278-410e-b0ee-3f6844c5b9ad" />


Inteligencia competitiva de cartelera: Cinemex vs Cinépolis (México).

- `project.md`: cómo funcionan las APIs de ambas cadenas, modelo de datos y estado del proyecto.
- `cinepolis_mx_cines.yaml`: catálogo de cines Cinépolis MX con slug, Vista ID, timezone y coordenadas.
- `scraper/`: capturas **nacionales** de cartelera (Cinépolis 499 cines, Cinemex 278) tres veces al día, con diff de cambios en
  SQLite; `scraper/plazas.py` define las plazas comparables (CDMX, Guadalajara, Monterrey);
  `scraper/sample.py` mide aforo, ocupación (planos de asientos de Cinépolis tras el inicio, cada hora), precios y
  dulcería; `scraper/delivery.py` lee la dulcería a domicilio en Rappi y DiDi Food; `scraper/health.py` vigila la captura.
- `analytics/`: consultas de negocio sobre la base (funciones puras, sin dependencias).
- `auth/`: cuentas, sesiones y enlaces de acceso del dashboard (SQLite propia, `data/app.db`; correo por SES);
  `make user-create` crea el primer admin.
- `app.py` + `ui/` + `views/`: dashboard Streamlit con login por usuario (roles admin y consulta) y páginas de cartelera,
  dulcería, datos (explorador de tablas) y, para admin, usuarios y operaciones (estado de la plataforma), que solo pintan lo
  que devuelve `analytics/`, `auth/` y `scraper.health`.
- Todo vive en SQLite (`data/snapshots.db` de la captura, `data/app.db` de las cuentas), con respaldo diario al bucket;
  el archivo histórico en PostgreSQL se retiró el 2026-09-25 (tag `pre-sqlite-only`).
- `deploy/`: systemd, respaldo, Caddy y la salida por Cloudflare WARP hacia Cinépolis (su WAF bloquea las IPs de AWS)
  para correr todo en un servidor (`deploy/README.md`).
- `docs/`: diagrama de despliegue (`arquitectura_aws.py`), dimensionamiento del servidor e investigación.
- `marketing/`: landing page pública del producto (Next.js, independiente del resto del repo, sitio estático). Ver
  `marketing/README.md` y `marketing/design.md`.
- `ARCHITECTURE.md`: qué proceso toca qué dato y qué lo programa. `AGENTS.md`: convenciones del repo. `make help`: comandos.
- Calidad: `make check` (lint con `ruff`, imports sin dependencias, `pytest`, con la captura de ambas cadenas contra
  respuestas reales grabadas) corre en el hook `pre-push` (`make hooks` lo
  activa) y en GitHub Actions, que mueve la rama `stable` cuando pasa; el servidor despliega `stable` en los siguientes 15 min.

```sh
make snapshot                                # una captura de ambas cadenas (~5 min)
make health                                  # estado de la captura
sqlite3 data/snapshots.db "SELECT * FROM snapshot ORDER BY id DESC LIMIT 4;"
```

Dashboard local (sin servicios externos: las cuentas se crean en `data/app.db` al primer uso):

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dashboard.txt -r requirements-dev.txt
make hooks                                            # pre-push: make check (lint, imports, pruebas)
make user-create EMAIL=tu@correo NAME="Tu Nombre" ROLE=admin   # imprime el enlace para elegir la contraseña
.venv/bin/streamlit run app.py
```

Lo programado vive en `jobs/registry.py` (tabla en `ARCHITECTURE.md`, "Programación"); cada trabajo se corre a mano con
`make job KEY=llave`. En la Mac, `make launchd-load` genera en `data/launchd/` un agente por cada trabajo marcado para la
Mac (cartelera, planos, precios, preventas, salud, delivery) y los carga. El repo debe estar fuera de `~/Documents`,
`~/Desktop` y `~/Downloads`: macOS no deja que launchd lea esas carpetas ("Operation not permitted").

```sh
make launchd-load      # cargar los agentes
make launchd-unload    # detenerlos (antes de mover el scraper al servidor)
```
