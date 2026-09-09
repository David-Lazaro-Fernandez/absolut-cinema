# absolut-cinema

Inteligencia competitiva de cartelera: Cinemex vs Cinépolis (México).

- `project.md`: cómo funcionan las APIs de ambas cadenas, modelo de datos y estado del proyecto.
- `cinepolis_mx_cines.yaml`: catálogo de cines Cinépolis MX con slug, Vista ID, timezone y coordenadas.
- `scraper/`: snapshots de cartelera de la plaza piloto (CDMX) cada 15 min, con diff de cambios en SQLite;
  `scraper/sample.py` muestrea aforo, ocupación (planos de asientos de Cinépolis) y precios de ambas cadenas.
- `analytics/`: consultas de negocio sobre la base (funciones puras, sin dependencias).
- `app.py` + `ui/` + `views/`: dashboard Streamlit con dos páginas (cartelera y dulcería) que solo pintan lo que devuelve `analytics/`.
- `deploy/`: systemd, respaldo y Caddy para correr todo en un servidor. Ver `deploy/README.md`.

```sh
/usr/bin/python3 -m scraper.run              # un snapshot de ambas cadenas (~5 min)
sqlite3 data/snapshots.db "SELECT * FROM snapshot ORDER BY id DESC LIMIT 4;"
```

Dashboard local:

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dashboard.txt
.venv/bin/streamlit run app.py
```

Programación con launchd (cada 15 min) mientras no esté en el servidor. El repo debe estar fuera de `~/Documents`, `~/Desktop` y `~/Downloads`: macOS no deja que launchd lea esas carpetas ("Operation not permitted").

```sh
cp scraper/com.absolut-cinema.scraper.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.absolut-cinema.scraper.plist
# detener: launchctl bootout gui/$(id -u)/com.absolut-cinema.scraper
```
