
# matine

<img width="1194" height="584" alt="Frame 1 (2)" src="https://github.com/user-attachments/assets/526e5100-e278-410e-b0ee-3f6844c5b9ad" />


Matiné captura la cartelera de los cines de México y la convierte en datos comparables: funciones, precios, aforo,
ocupación y dulcería. Captura Cinemex y Cinépolis en todo el país, y la Cineteca Nacional, la Cineteca FICG y el
Cineforo (Guadalajara) y la Cineteca Nuevo León (Monterrey).

Sobre la misma base hay tres productos:

- **Dashboard** (`app.py`, `ui/`, `views/`): comparación entre cadenas por plaza o nacional, con login por usuario.
- **API pública** (`api/`): la búsqueda de "¿A dónde ir?", funciones cerca de un punto que caben en un presupuesto.
- **Sitio público** (`marketing/`): la página de Matiné y la demo "¿A dónde ir?". Next.js estático, independiente del
  resto del repo. Ver `marketing/README.md`.

## Estructura

- `scraper/`: captura de cartelera tres veces al día, con diff de cambios en SQLite. También mide aforo, ocupación,
  precios y dulcería (`sample.py`), y la dulcería a domicilio en Rappi y DiDi Food (`delivery.py`). `health.py` vigila
  la captura. `plazas.py` define las plazas comparables (CDMX, Guadalajara, Monterrey).
- `analytics/`: consultas de negocio sobre la base. Funciones puras, sin dependencias. Las usan el dashboard y la API.
- `auth/`: cuentas, sesiones y enlaces de acceso del dashboard (`data/app.db`; correo por SES).
- `jobs/`: el calendario de todo lo programado (`registry.py`). De ahí salen las unidades de systemd y los agentes de
  launchd.
- `deploy/`: systemd, respaldo, Caddy y la salida por Cloudflare WARP hacia Cinépolis (su WAF bloquea las IPs de AWS).
  Ver `deploy/README.md`.
- `docs/`: diagrama de despliegue, dimensionamiento del servidor e investigación.
- Datos: todo vive en SQLite (`data/snapshots.db` de la captura, `data/app.db` de las cuentas), con respaldo diario.

Documentación: `project.md` (APIs de las cadenas, modelo de datos, decisiones), `ARCHITECTURE.md` (qué proceso toca qué
dato), `DESIGN.md` (diseño del dashboard), `AGENTS.md` (convenciones). `make help` lista los comandos.

## Uso local

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
make hooks                                     # pre-push: make check (lint, imports, pruebas)
make snapshot                                  # una captura completa (~5 min)
make health                                    # estado de la captura
make user-create EMAIL=tu@correo NAME="Tu Nombre" ROLE=admin   # imprime el enlace para elegir la contraseña
make dashboard                                 # dashboard en Streamlit
make api                                       # API pública en http://localhost:8000/docs
make marketing-dev                             # sitio público (npm install una vez en marketing/)
```

Cada trabajo programado se corre a mano con `make job KEY=llave` (llaves en `jobs/keys.py`). En la Mac,
`make launchd-load` carga un agente por cada trabajo marcado para la Mac y `make launchd-unload` los detiene. El repo debe
estar fuera de `~/Documents`, `~/Desktop` y `~/Downloads`: macOS no deja que launchd lea esas carpetas.

## Calidad y despliegue

`make check` corre `ruff`, la prueba de imports sin dependencias y `pytest`, con la captura de ambas cadenas contra
respuestas reales grabadas. Corre en el hook `pre-push` y en GitHub Actions. Cuando pasa en `main`, Actions mueve la rama
`stable`, y el servidor la despliega en los siguientes 15 minutos.
