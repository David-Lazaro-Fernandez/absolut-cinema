# Despliegue en un servidor (droplet de DigitalOcean o EC2)

Todo vive en `/opt/absolut-cinema` con el usuario de sistema `absolut`. Reemplaza al launchd de la Mac,
que deja huecos en la serie cada vez que la laptop duerme.

## Primera vez

```sh
# En el servidor, como root (Ubuntu 24.04):
git clone <repo> /opt/absolut-cinema
bash /opt/absolut-cinema/deploy/install.sh
```

`install.sh` fija la zona horaria en `America/Mexico_City`, crea el usuario, el venv del dashboard,
enlaza los units de systemd y los habilita:

| Unit | Qué hace |
| --- | --- |
| `absolut-cinema-scraper.timer` | corre `python3 -m scraper.run` en :00, :15, :30 y :45 |
| `absolut-cinema-dashboard.service` | Streamlit en `127.0.0.1:8501` |
| `absolut-cinema-backup.timer` | `backup.sh` a las 05:07: copia de la base y sync del crudo al bucket |

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
