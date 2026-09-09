
# absolut-cinema

<img width="1194" height="584" alt="Frame 1 (2)" src="https://github.com/user-attachments/assets/526e5100-e278-410e-b0ee-3f6844c5b9ad" />


Inteligencia competitiva de cartelera: Cinemex vs Cinépolis (México).

- `project.md`: cómo funcionan las APIs de ambas cadenas, modelo de datos y estado del proyecto.
- `cinepolis_mx_cines.yaml`: catálogo de cines Cinépolis MX con slug, Vista ID, timezone y coordenadas.
- `scraper/`: capturas de cartelera de la plaza piloto (CDMX) tres veces al día, con diff de cambios en SQLite;
  `scraper/sample.py` mide aforo, ocupación (planos de asientos de Cinépolis tras el inicio, cada hora), precios y
  dulcería; `scraper/delivery.py` lee la dulcería a domicilio en Rappi y DiDi Food; `scraper/health.py` vigila la captura.
- `analytics/`: consultas de negocio sobre la base (funciones puras, sin dependencias).
- `app.py` + `ui/` + `views/`: dashboard Streamlit con dos páginas (cartelera y dulcería) que solo pintan lo que devuelve `analytics/`.
- `sync/`: archivo histórico en PostgreSQL: copia lo nuevo de SQLite y reconstruye la historia de cada función desde el
  crudo (`make sync`, cada 30 min). Postgres local con `make pg-up pg-schema`; el esquema en `deploy/postgres/schema.sql`.
- `deploy/`: systemd, respaldo y Caddy para correr todo en un servidor (`deploy/README.md`); `deploy/docker-compose.dev.yml`
  levanta Postgres 16 y pgAdmin para desarrollo.
- `docs/`: diseño del archivo histórico (`postgres-esquema.md`), diagrama de despliegue (`arquitectura_aws.py`) e investigación.
- `ARCHITECTURE.md`: qué proceso toca qué dato y qué lo programa. `AGENTS.md`: convenciones del repo. `make help`: comandos.

```sh
make snapshot                                # una captura de ambas cadenas (~5 min)
make health                                  # estado de la captura
sqlite3 data/snapshots.db "SELECT * FROM snapshot ORDER BY id DESC LIMIT 4;"
```

Dashboard local:

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dashboard.txt
.venv/bin/streamlit run app.py
```

Programación con launchd mientras no esté en el servidor: cinco agentes (cartelera tres veces al día, planos cada hora,
diario, delivery, sync a Postgres) que ejecutan targets de `make`. El repo debe estar fuera de `~/Documents`, `~/Desktop` y `~/Downloads`:
macOS no deja que launchd lea esas carpetas ("Operation not permitted").

```sh
make launchd-load      # cargar los agentes
make launchd-unload    # detenerlos (antes de mover el scraper al servidor)
```
