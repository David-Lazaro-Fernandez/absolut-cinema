# Despliegue en un servidor (EC2 en la cuenta de AWS de Cinemex)

Todo vive en `/opt/absolut-cinema` con el usuario de sistema `absolut`. Reemplaza al launchd de la Mac,
que deja huecos en la serie cada vez que la laptop duerme.

**Servidor de destino (decisión 2026-09-09):** EC2 `t4g.medium` (ARM Graviton2, 2 vCPU, 4 GB) con 30 GB
de EBS gp3 y la zona horaria en `America/Mexico_City`. El pico medido de memoria es ~600 MB (una captura
y el dashboard a la vez) y la base crece ~7 MB al día, así que 4 GB y 30 GB dan margen para años. Por qué
esa instancia y no otra: `docs/ec2-sizing.md`. Cómo se crea la VPC, el rol de IAM, el bucket y la
instancia: `docs/aws-setup.md`. Los pasos de abajo valen igual en cualquier Ubuntu 24.04.

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
mostraría un aviso de "aún no hay datos"), y con `deploy/units.sh` enlaza las unidades de systemd y enciende los timers.

**Las unidades se generan desde `jobs/registry.py`** (`make units`) y viven en `deploy/systemd/`: una unidad
`absolut-cinema-{llave}.service` + `.timer` por trabajo, y cada una ejecuta `make job KEY=llave`. La tabla de trabajos,
cadencias y topes está en `ARCHITECTURE.md` ("Programación"), generada del mismo registro. Además, siempre encendido,
`absolut-cinema-dashboard.service` (Streamlit en `127.0.0.1:8501`, escrito a mano).

`deploy/units.sh` (idempotente; lo llaman `install.sh` y, si cambió alguna unidad, `update.sh`) enlaza todo lo de
`deploy/systemd/`, **apaga y quita las unidades de absolut-cinema que ya no están en el repo** (una llave renombrada,
como `scraper` → `snapshot` el 2026-09-25) y enciende los timers que el registro marca como encendidos. Si el registro marcara alguno como apagado,
quedaría enlazado y se enciende con `systemctl enable --now absolut-cinema-{llave}.timer`.

Cada corrida pasa por `jobs.run`: candado por llave (si el timer y una corrida a mano coinciden, la segunda se salta),
tope de tiempo del registro (systemd tiene 5 min más de margen), reintentos donde el registro los pide (respaldo) y una
línea en `data/logs/jobs.jsonl` con duración, resultado y **pico de memoria**, que la página Operaciones muestra por
trabajo. Los timers diarios van a :07 para no coincidir con el tick de planos; si coinciden, SQLite espera hasta 60 s
(`timeout` de `store.connect`). El aforo nacional de Cinemex se lanza a mano (`make capacity-cinemex PLAZAS=all`).

Después de instalar:

1. Copiar la base existente de la Mac para no perder la historia:
   `rsync -a ~/absolut-cinema/data/ root@SERVIDOR:/opt/absolut-cinema/data/` y
   `chown -R absolut:absolut /opt/absolut-cinema/data`. Apagar antes el launchd local
   (`make launchd-unload` en la Mac) para que no haya dos escritores.
2. Editar `/etc/absolut-cinema.env` con el bucket de respaldo y, si hace falta, el endpoint de Spaces.
   Credenciales del bucket en `/home/absolut/.aws/credentials`.
3. Editar `/etc/caddy/Caddyfile`: dominio (con DNS apuntando al servidor). El `basic_auth` es una segunda puerta
   opcional mientras no haya dominio ni TLS; con el dominio en producción, quitar ese bloque. Luego `systemctl reload caddy`.
4. Dar de alta el acceso por usuario (siguiente sección): variables `AC_BASE_URL` y `AC_MAIL_*` y el primer admin con
   `make user-create`. Las cuentas viven en `data/app.db`, que se crea sola.

## Operación

```sh
systemctl list-timers 'absolut-cinema-*'            # próximas ejecuciones
tail -f /opt/absolut-cinema/data/logs/run.log      # una línea por cadena y snapshot
journalctl -u absolut-cinema-dashboard -f          # logs de Streamlit
systemctl start absolut-cinema-snapshot.service    # forzar una captura de cartelera ahora
systemctl start absolut-cinema-backup.service      # forzar un respaldo ahora
systemctl start absolut-cinema-health.service      # reporte de salud ahora (también: make health)
cat /opt/absolut-cinema/data/logs/health.log       # una línea por día
tail /opt/absolut-cinema/data/logs/jobs.jsonl      # una línea por corrida: duración, resultado, memoria
```

**Alcance de la captura.** Nacional por defecto (Cinépolis ~155 ciudades, Cinemex 31 estados; las dos cadenas se
descargan en paralelo y la captura tarda ~17 min desde la Mac con el ritmo frenado de Cinépolis, algo más desde el servidor vía WARP;
tope de 45 min del trabajo `snapshot` en `jobs/registry.py`). Para
acotarla, `AC_CINEPOLIS_CITIES` y `AC_CINEMEX_STATES` en el `.env`. Los planos de asientos (trabajo `seats`) solo se toman
en las plazas de `AC_SEATS_PLAZAS` (por defecto `cdmx`; claves de `scraper/plazas.py`): se amplía cuando el registro de
cobertura de la página Operaciones diga qué plazas pesan. Al cambiar el `.env`, `systemctl daemon-reload` no hace falta
(lo leen los units al arrancar cada corrida).

Actualizar código: lo hace solo el despliegue diario (sección siguiente). Para forzarlo ahora: `make deploy` como root
(o `systemctl start absolut-cinema-deploy.service`). Los timers toman el código nuevo en su siguiente ejecución.

## Despliegue diario y commit estable

No se despliega cada push: un piloto sin entornos de staging no lo necesita y una recarga a media mañana molestaría
al cliente. En su lugar hay dos piezas desacopladas:

1. **GitHub Actions decide qué es seguro** (`.github/workflows/tests.yml`). En cada push a `main` corre `pytest` y
   comprueba que `scraper/` y `analytics/` siguen importando sin dependencias externas. Si todo pasa, mueve la rama
   `stable` a ese commit; si algo falla, `stable` no se mueve y el commit queda en rojo en GitHub. La rama `stable` la
   mueve solo el workflow: no se toca a mano. Así el "último commit seguro" siempre es `origin/stable`.
2. **El servidor decide cuándo** (`deploy/update.sh`, `make deploy`, `absolut-cinema-deploy.timer` a las 07:07, hora de
   poco uso y antes de la captura de las 07:30). Trae `origin/stable`, y solo si hay algo nuevo: `git reset --hard` a ese
   commit como el usuario `absolut`, reinstala el venv si cambió algún `requirements-*.txt`, `deploy/units.sh` si cambió una
   unidad en `deploy/`, reinicia el dashboard y espera a que `/_stcore/health` responda. Escribe una línea por corrida en
   `data/logs/deploy.log` y sale con 1 si el dashboard no levanta (queda visible en `systemctl list-timers`). No toca
   `data/`: los cambios de esquema de ambas bases son aditivos y se aplican solos al conectar (`store.py`, `auth/db.py`).

```sh
tail -5 /opt/absolut-cinema/data/logs/deploy.log        # qué se desplegó y cuándo
make deploy                                              # desplegar ahora el último estable
REF=<commit> make deploy                                 # volver a un commit anterior (o adelantar uno concreto)
git -C /opt/absolut-cinema log -1 --oneline              # qué corre hoy
```

Los timers del scraper no se reinician: Python ya cargó sus módulos al arrancar cada corrida, y la siguiente toma el
código nuevo. El único reinicio es el del dashboard, unos segundos a las 07:07.

## Acceso por usuario y correo (SES)

El dashboard pide correo y contraseña (`auth/`, `ui/session.py`) con dos roles: `admin` (gestiona cuentas en la página
Usuarios y ve todo) y `viewer` (Cartelera, Dulcería y el explorador Datos). Las cuentas viven en su propia base SQLite,
`data/app.db` (`AC_APP_DB` para moverla), que escribe solo `auth/`; se crea con su esquema al primer uso y entra en el
respaldo diario.

```sh
# En /etc/absolut-cinema.env: AC_BASE_URL=https://DOMINIO   AC_MAIL_BACKEND=ses   AC_MAIL_FROM="Absolut Cinema <no-responder@DOMINIO>"
systemctl restart absolut-cinema-dashboard
sudo -u absolut make -C /opt/absolut-cinema user-create EMAIL=quien@cinemex.com NAME="Nombre Apellido" ROLE=admin
```

`user-create` imprime el enlace de invitación además de enviarlo (vale 72 h, un solo uso); con `NOMAIL=1` solo lo
imprime, para entregarlo por otro canal. Después, el admin crea el resto de las cuentas desde la página Usuarios. Más
comandos: `make user-list`, `make user-reset EMAIL=…` (enlace nuevo), `make user-deactivate EMAIL=…`, `make user-activate EMAIL=…`.

**Correo.** `AC_MAIL_BACKEND=console` (default) no envía nada: escribe el correo completo en `data/logs/mail.log`.
`ses` envía por Amazon SES con las credenciales del rol de la instancia (`ses:SendEmail` en la política, ver
`docs/aws-setup.md`), `AWS_REGION` del entorno y `AC_MAIL_FROM` como identidad verificada. Pasos en SES (consola, región
de la instancia): crear la identidad del dominio y publicar sus tres CNAME de DKIM en el DNS; mientras la cuenta esté en
*sandbox* solo llegan correos a direcciones verificadas a mano, así que pedir "production access" (caso de uso: correos
transaccionales de acceso, menos de 100 al mes) o verificar los correos del personal de Cinemex. Probar con
`make user-reset EMAIL=…` y `journalctl -u absolut-cinema-dashboard`.

**Cookie y seguridad.** La sesión dura 30 días y se extiende con el uso; se guarda solo su sha256 y se revoca al cerrar
sesión, cambiar la contraseña o desactivar la cuenta (surte efecto en ≤ 60 s). Con `AC_BASE_URL` en `https` la cookie
lleva `Secure`. Diez contraseñas malas seguidas bloquean la cuenta 15 min. "Olvidé mi contraseña" responde igual exista o
no el correo y emite a lo más tres enlaces por hora (valen 60 min). Streamlit no permite cookies `HttpOnly`; la
mitigación es el token aleatorio con hash en base y la revocación.

## Salida por Cloudflare WARP para Cinépolis

`api-g.cinepolis.com` está detrás de Cloudflare y su WAF bloquea los rangos de AWS por ASN (verificado 2026-09-10:
403 "Attention Required" directo desde EC2, 200 saliendo por WARP; Cinemex, Rappi y DiDi no lo necesitan). `install.sh`
instala el cliente `cloudflare-warp` en modo proxy (SOCKS5 en `127.0.0.1:40000`, registro gratuito, sin cuenta ni
relación con el WARP de ninguna empresa) y `privoxy` como puente HTTP (`127.0.0.1:8118`, `deploy/privoxy.config`).
El scraper manda por ahí solo los hosts de `AC_EGRESS_PROXY_HOSTS`; el resto sale directo.

```sh
warp-cli status                                    # debe decir Connected
systemctl status warp-svc privoxy                  # ambos activos
curl -s -x http://127.0.0.1:8118 https://ipinfo.io/json | grep -E '"org"|"country"'   # AS13335 Cloudflare
warp-cli --accept-tos connect                      # reconectar si se cayó
```

Si el túnel cae, el snapshot de Cinépolis falla con `Blocked` (403 con HTML) o con `URLError … (vía proxy …)` si
Privoxy no responde; `make health` lo reporta como captura fallida. Para volver a salir directo, vaciar
`AC_EGRESS_PROXY` en `/etc/absolut-cinema.env`.

## Restaurar

El respaldo diario (`deploy/backup.sh`, 05:07) deja en el bucket tres cosas: `db/snapshots-FECHA.db.gz` (la base de la
captura), `app/app-FECHA.db.gz` (cuentas y sesiones) y `raw/` (el crudo de cada captura, del que se puede reconstruir
cualquier historia). Las copias de las bases salen de `.backup` de SQLite: consistentes aunque la captura o el dashboard
estén escribiendo. Simulacro del 2026-09-25 en local: `snapshots.db` de 810 MB se copia en 4 s, pesa 53 MB comprimida y
la copia restaurada pasa `PRAGMA integrity_check` y abre con `analytics` y `auth`.

```sh
cd /tmp && aws s3 cp s3://BUCKET/db/snapshots-FECHA.db.gz . && aws s3 cp s3://BUCKET/app/app-FECHA.db.gz .
gunzip snapshots-FECHA.db.gz app-FECHA.db.gz
sqlite3 snapshots-FECHA.db "PRAGMA integrity_check;"      # debe decir ok
sqlite3 app-FECHA.db "PRAGMA integrity_check;"
systemctl stop 'absolut-cinema-*.timer' absolut-cinema-dashboard
rm -f /opt/absolut-cinema/data/snapshots.db-wal /opt/absolut-cinema/data/snapshots.db-shm \
      /opt/absolut-cinema/data/app.db-wal /opt/absolut-cinema/data/app.db-shm
mv snapshots-FECHA.db /opt/absolut-cinema/data/snapshots.db && mv app-FECHA.db /opt/absolut-cinema/data/app.db
chown absolut:absolut /opt/absolut-cinema/data/snapshots.db /opt/absolut-cinema/data/app.db
aws s3 sync s3://BUCKET/raw/ /opt/absolut-cinema/data/raw/ && chown -R absolut:absolut /opt/absolut-cinema/data/raw
systemctl start absolut-cinema-dashboard && /opt/absolut-cinema/deploy/units.sh   # vuelve a encender los timers
```

La siguiente captura corrige sola la cartelera vigente (el diff contra lo restaurado registra lo que cambió en el hueco).
Las sesiones abiertas después de la fecha del respaldo se pierden: esas personas vuelven a entrar.
