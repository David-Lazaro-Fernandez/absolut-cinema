# absolut-cinema

Inteligencia competitiva de cartelera: Cinemex vs Cinépolis (México).

- `project.md`: cómo funcionan las APIs de ambas cadenas, modelo de datos y estado del proyecto.
- `cinepolis_mx_cines.yaml`: catálogo de cines Cinépolis MX con slug, Vista ID, timezone y coordenadas.
- `scraper/`: snapshots de cartelera de la plaza piloto (CDMX) cada 15 min, con diff de cambios en SQLite.

```sh
/usr/bin/python3 -m scraper.run              # un snapshot de ambas cadenas (~5 min)
sqlite3 data/snapshots.db "SELECT * FROM snapshot ORDER BY id DESC LIMIT 4;"
```

Programación con launchd (cada 15 min). El repo debe estar fuera de `~/Documents`, `~/Desktop` y `~/Downloads`: macOS no deja que launchd lea esas carpetas ("Operation not permitted").

```sh
cp scraper/com.absolut-cinema.scraper.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.absolut-cinema.scraper.plist
# detener: launchctl bootout gui/$(id -u)/com.absolut-cinema.scraper
```
