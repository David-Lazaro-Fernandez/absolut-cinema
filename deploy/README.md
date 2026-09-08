# Despliegue en un servidor (droplet de DigitalOcean o EC2)

Todo vive en `/opt/absolut-cinema` con el usuario de sistema `absolut`. Reemplaza al launchd de la Mac,
que deja huecos en la serie cada vez que la laptop duerme.

## Primera vez

```sh
# En el servidor, como root (Ubuntu 24.04):
git clone <repo> /opt/absolut-cinema
bash /opt/absolut-cinema/deploy/install.sh
```

`install.sh` instala todas las dependencias (paquetes del sistema: `python3`, `python3-venv`, `sqlite3`,
`awscli`, `caddy`; y el venv del dashboard con `requirements-dashboard.txt`; el scraper solo usa la librería
estándar de `/usr/bin/python3`), fija la zona horaria en `America/Mexico_City`, crea el usuario, corre un
**primer snapshot si no existe `data/snapshots.db`** (el dashboard solo lee esa base, así que sin ella
mostraría un aviso de "aún no hay datos"), enlaza los units de systemd y los habilita:

| Unit | Cadencia | Qué hace (equivalente en `make`) |
| --- | --- | --- |
| `absolut-cinema-scraper.timer` | :00, :15, :30, :45 | snapshot de cartelera + planos a T−60 + planos post-inicio (`make tick`) |
| `absolut-cinema-prices.timer` | diario 06:07 | muestreo de precios (`make prices`) |
| `absolut-cinema-health.timer` | diario 08:07 | reporte de salud en `data/logs/health.log`; falla si hay huecos o errores (`make health`) |
| `absolut-cinema-capacity.timer` | día 1, 04:07 | refresco mensual del aforo de Cinépolis (`make capacity REFRESH=1`) |
| `absolut-cinema-backup.timer` | diario 05:07 | `backup.sh`: copia de la base y sync del crudo al bucket (`make backup`) |
| `absolut-cinema-calibrate-cinemex.timer` | diario 19:07, **apagado** | calibración del semáforo de Cinemex, 60 funciones por corrida; abre órdenes de checkout, por eso `install.sh` lo enlaza pero no lo habilita (`make calibrate-cinemex`) |
| `absolut-cinema-dashboard.service` | siempre | Streamlit en `127.0.0.1:8501` |

Los timers que escriben van a :07 para no coincidir con el arranque de un snapshot; si coinciden, SQLite
espera hasta 60 s (`timeout` de `store.connect`). Aforo y calibración de Cinemex se lanzan a mano
(`make capacity-cinemex`, `make calibrate-cinemex`) o encendiendo el timer:
`systemctl enable --now absolut-cinema-calibrate-cinemex.timer`.

Después de instalar:

1. Copiar la base existente de la Mac para no perder la historia:
   `rsync -a ~/absolut-cinema/data/ root@SERVIDOR:/opt/absolut-cinema/data/` y
   `chown -R absolut:absolut /opt/absolut-cinema/data`. Apagar antes el launchd local
   (`launchctl bootout gui/$(id -u)/com.absolut-cinema.scraper`) para que no haya dos escritores.
2. Editar `/etc/absolut-cinema.env` con el bucket de respaldo y, si hace falta, el endpoint de Spaces.
   Credenciales del bucket en `/home/absolut/.aws/credentials`.
3. Editar `/etc/caddy/Caddyfile`: dominio (con DNS apuntando al servidor) y hash de la contraseña
   (`caddy hash-password`). Luego `systemctl reload caddy`.

## Operación

```sh
systemctl list-timers 'absolut-cinema-*'            # próximas ejecuciones
tail -f /opt/absolut-cinema/data/logs/run.log      # una línea por cadena y snapshot
journalctl -u absolut-cinema-dashboard -f          # logs de Streamlit
systemctl start absolut-cinema-scraper.service     # forzar un snapshot ahora
systemctl start absolut-cinema-backup.service      # forzar un respaldo ahora
systemctl start absolut-cinema-health.service      # reporte de salud ahora (también: make health)
cat /opt/absolut-cinema/data/logs/health.log       # una línea por día
```

Actualizar código: `cd /opt/absolut-cinema && sudo -u absolut git pull && systemctl restart absolut-cinema-dashboard`.
El scraper toma el código nuevo en la siguiente ejecución del timer.

## Restaurar

```sh
aws s3 cp s3://BUCKET/db/snapshots-FECHA.db.gz . && gunzip snapshots-FECHA.db.gz
systemctl stop absolut-cinema-scraper.timer
mv snapshots-FECHA.db /opt/absolut-cinema/data/snapshots.db && chown absolut:absolut /opt/absolut-cinema/data/snapshots.db
systemctl start absolut-cinema-scraper.timer
```
