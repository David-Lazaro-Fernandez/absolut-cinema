# Dimensionamiento EC2 para Absolut Cinema

## Análisis de cargas

### Scraper (captura de cartelera)
- **Frecuencia:** 3×/día (07:30, 13:30, 20:30 CDMX)
- **Duración:** 1–7 min (según si se publica semana siguiente)
- **Llamadas:** ~260 CDMX (ambas cadenas)
- **CPU:** bajo (I/O-bound, requests HTTP)
- **RAM:** ~100–150 MB por corrida
- **Concurrencia:** secuencial (sin paralelismo)

### Planos de asientos (post-inicio)
- **Frecuencia:** cada hora, :50
- **Duración:** ~1.7 s por plano, ~1,600 llamadas/42 min en pasada inicial
- **Pausa entre llamadas:** 0.6 s (sin sobrecargar Vista)
- **CPU:** bajo (I/O-bound)
- **RAM:** ~50 MB por corrida

### Precios, dulcería Cinépolis
- **Frecuencia:** diario 06:00 (precios) y diario (concessions)
- **Duración:** precios ~1 min, concessions ~100 s para 74 cines
- **CPU:** bajo
- **RAM:** ~50 MB

### Dulcería a domicilio (Rappi, DiDi Food)
- **Frecuencia:** diario 15:00
- **Duración:** scraping HTML (~90 s para 229 tiendas)
- **CPU:** bajo
- **RAM:** ~80 MB

### Health check
- **Frecuencia:** diario 06:00
- **Duración:** <1 s (queries SQLite)
- **CPU:** mínimo
- **RAM:** mínimo

### Dashboard Streamlit
- **Carga base:** ~300 MB RAM (proceso Python + deps)
- **Por usuario concurrente:** +50–100 MB (caché, datos en memoria)
- **CPU:** bajo en idle, picos al cargar datos (queries SQLite, Altair rendering)
- **Acceso:** 24/7, pero tráfico bajo esperado (1–3 usuarios)

## Picos de carga coincidentes

Peor caso observado:
- **07:30:** captura de cartelera (1–7 min) + health check + precios
- **13:30:** captura + planos (por hora, :50)
- **20:30:** captura + planos + delivery

Si un usuario consulta el dashboard durante un snapshot, se suma:
- Snapshot: ~150 MB (scraper + crudo en memoria)
- Health: <10 MB
- Precios: ~50 MB
- Planos: ~50 MB
- Dashboard: ~300 MB
- SQLite WAL: ~50 MB (escritor + lector simultáneamente)
- **Total observado:** ~600 MB pico

## Operaciones de escritura y almacenamiento (medido 2026-09-09)

Todo lo de esta sección sale de `data/snapshots.db` con 3 días de historia, no de estimaciones.

### Escrituras por día (cadencia de 3 capturas/día)

| Tabla | Patrón | Filas por corrida | Row-ops/día |
| --- | --- | --- | --- |
| `current_showtime` | `DELETE` de la cadena + `INSERT` de todas sus filas (`replace_current`; desde el 2026-09-25 solo la diferencia, `apply_current`) | 51,468 (Cinemex 28,346 + Cinépolis 23,122) | **308,808** |
| `event` | solo `INSERT`, acumula | ~2,300 por corrida | ~7,000 |
| `occupancy_sample` | solo `INSERT`, cada hora | ~90 por pase | ~1,750 |
| `concession_price` | solo `INSERT`, 74 cines renovados cada 7 días | 10,942 por pasada | ~1,563 |
| `delivery_price` | solo `INSERT`, 229 tiendas cada 7 días | 6,778 por pasada | ~968 |
| `price_sample` | solo `INSERT`, diario | ~300 | ~300 |
| `auditorium` | `INSERT`, mensual | 1,425 salas | ~48 |
| `snapshot` | 1 `INSERT` + 1 `UPDATE` por cadena y corrida | 2 | 12 |
| **Total** | | | **~320,000** |

**El 96 % de las escrituras es el `DELETE` + `INSERT` completo de `current_showtime`.** La información
nueva de verdad son ~11,600 filas al día; el resto es reescribir el estado vigente entero tres veces.
En SQLite eso cuesta una transacción local y no importa. En Postgres el mismo patrón deja 308,808
tuplas muertas al día para autovacuum, y en un motor que cobra por escritura (DynamoDB) se paga
completo. (Desde entonces `current_showtime` se escribe por diferencia, `store.apply_current`: altas, cambios y
cierres, no la tabla entera.)

### Crecimiento en disco

| Concepto | Medido | Al mes | Al año |
| --- | --- | --- | --- |
| `snapshots.db` | 80 MB con 3 días (la mayoría del régimen viejo de 15 min) | ~0.21 GB | **~2.5 GB** |
| `data/raw/` comprimido | 0.65 MB por corrida → ~2 MB/día con 3 capturas | ~60 MB | **~0.7 GB** |
| `data/logs/` | 136 KB en 3 días | ~1.4 MB | ~17 MB |

`current_showtime` no crece (se reemplaza, ~15 MB estables). Lo que crece sin límite es `event`
(883 bytes por fila, ~980 con sus tres índices) y, más despacio, las tablas de muestreo.

**Consecuencia para EBS: 30 GB gp3 sobran para más de tres años.** El dimensionamiento inicial de
este documento pedía 100 GB por una estimación equivocada del crudo.

## Recomendación de instancia

### Candidatos (precios oficiales AWS t4g, ARM Graviton2)

| Instancia | vCPU | RAM | Precio/hora | Precio/mes (730h) | Caso |
| --- | --- | --- | --- | --- | --- |
| `t4g.nano` | 2 | 0.5 GB | 0.0042 USD | ~3.07 USD | **No.** Insuficiente. |
| `t4g.micro` | 2 | 1 GB | 0.0084 USD | ~6.13 USD | **No.** Apenas menos que `t4g.small`, insuficiente en pico. |
| `t4g.small` | 2 | 2 GB | 0.0168 USD | ~12.26 USD | ⚠️ Sin margen: la captura nacional llegó a 1.9 GB de pico (2026-09-25). Es la instancia actual; ver "Memoria en `t4g.small`". |
| **`t4g.medium`** | **2** | **4 GB** | **0.0336 USD** | **~24.53 USD** | ✅ **Recomendado** mientras la captura no tenga memoria acotada. |
| `t3.medium` (ref) | 2 | 4 GB | — | ~37 USD | Intel; más caro, igual performance. |

### Argumento para `t4g.medium`

1. **Overhead base:** Streamlit + Python runtime ≈ 400 MB.
2. **Pico scraper:** +300 MB → 700 MB.
3. **Pico dashboard:** +1 usuario en Streamlit durante captura → ~1 GB.
4. **Margen de seguridad:** hasta 4 GB sin swap (swap mata el rendimiento en EBS).
5. **CPU:** 2 vCPU con crédito de ráfaga; todo el trabajo es I/O-bound (HTTP con pausas de 0.6 s),
   así que la CPU nunca es el cuello de botella. Un snapshot y Streamlit conviven sin presión.
6. **EBS:** 30 GB gp3 → más de tres años de base, crudo y logs.
7. **ARM Graviton2:** Python, Streamlit y SQLite corren igual; ~33 % más barato que `t3.medium`.

`t4g.small` (2 GB, ~12.26 USD/mes) también funcionaría hoy: el pico medido es ~600 MB. Se recomienda
`medium` por el margen, porque la diferencia son 12 USD al mes y porque el pico crece con cada
usuario concurrente del dashboard.

## Decisión de almacenamiento (2026-09-25): solo SQLite

Se descartó PostgreSQL en RDS: el `db.t4g.micro` multi-AZ costaba ~22.50 USD/mes, casi la mitad de la cuenta, y el
volumen no lo pide. Lo que el cliente necesita es disponibilidad, no historia larga (el mercado de cine es volátil y la
historia de hace un año pesa poco en sus decisiones). Todo vive en SQLite en el disco de la instancia: `snapshots.db`
(la escribe solo la captura) y `app.db` (cuentas, la escribe solo `auth/`). La confiabilidad sale del respaldo diario de
ambas bases y del crudo al bucket (`deploy/backup.sh`) y de la restauración documentada en `deploy/README.md`. El código
del archivo en Postgres quedó en el tag `pre-sqlite-only`.

### Carga con la captura nacional (medido 2026-09-25)

Las cifras de arriba son del piloto CDMX. Con la captura nacional (278 cines de Cinemex, 496 de Cinépolis, ~22,500
funciones publicadas al día):

| Qué | Escrituras al día | Espacio al día |
| --- | --- | --- |
| `event` | ~50–65 mil filas | ~60–75 MB (≈ 22–27 GB al año) |
| `current_showtime` | ~50–65 mil operaciones; la tabla se mantiene en ~250 mil filas | 0 neto |
| Muestreos (planos, preventas, precios, dulcería) | ~12 mil filas | ~3 MB |

Para SQLite es poco: cada captura escribe ~20 mil filas en una transacción de segundos y los muestreos son ~5 mil
transacciones chicas al día. Las lecturas son de ~10 personas con caché (`TTL`) y en WAL no bloquean al escritor. Lo que
sí limita:

- **Memoria de la captura nacional.** `jobs.jsonl` registró 1,944 MB de pico el 2026-09-25, en una corrida que arrastraba
  13 días de hueco (348 mil eventos). Mientras no se acote (escribir por unidad en vez de armar todo el país en memoria),
  `t4g.small` no tiene margen: conviene `t4g.medium`.
- **Crecimiento de `event`.** ~22–27 GB al año: con 30 GB de EBS hace falta retención (90 días completos en SQLite y lo
  anterior compactado en el crudo o en el bucket) antes de un año.

Las dos van en su propio plan.

## Memoria en `t4g.small` (medido 2026-09-28)

El servidor corre hoy en un `t4g.small` (2 vCPU Graviton2, 2 GB). Graviton no tiene SMT: cada vCPU es un núcleo, así
que solo dos hilos corren en paralelo de verdad. Se agregó swap como paliativo, pero no ataca la causa.

**Qué pasó.** Un despliegue volvió a enlazar los timers y, con `Persistent=true`, snapshot, seats, delivery, backup y
health arrancaron juntos. El OOM killer mató primero a `warp-svc` (746 MB de RSS; systemd lo reinició en 15 s) y
después al `python3` del snapshot (664 MB), a media captura de Cinépolis. Cinemex ya se había escrito.

**Quién ocupa la memoria.**

| Proceso | Lenguaje | RSS | Qué lo baja |
| --- | --- | --- | --- |
| `warp-svc` | binario de Cloudflare | 746 MB | cambiarlo por `wireproxy` (ver abajo) |
| captura (`scraper.run`) | Python | 664 MB | procesar por unidad (ver abajo) |
| Caddy | Go | ~30–50 MB | nada |
| Privoxy | C | ~5 MB | sobra con `wireproxy` |

Reescribir en Rust no ataca lo principal: `warp-svc` no es nuestro y la captura pesa por su diseño, no por el lenguaje.

**Captura.** Medido en la Mac con el crudo del 2026-09-28 (~43 MB de JSON, 141 mil funciones):

| Paso | Pico |
| --- | --- |
| Los dos crudos cargados | 341 MB |
| Más `normalize.rows` (dicts, ~1.9 KB por fila) | 608 MB |
| Solo Cinépolis / solo Cinemex | 406 / 265 MB |

`scraper/run.py` descarga las tres cadenas en paralelo, retiene el crudo nacional completo y lo normaliza entero antes
de compararlo con `store.load_current`, que suma otras ~140 mil filas. CPython libera memoria, pero el asignador casi
nunca la regresa al sistema mientras el proceso vive: lo que cuenta es el pico. Si cada unidad (~1–2 MB de crudo) se
normaliza y se escribe al llegar, el pico estimado baja a ~150 MB.

**`wireproxy` en vez de `warp-svc` (prueba local, 2026-09-28).** `wgcf` registra una cuenta WARP gratuita y genera el
perfil de WireGuard. `wireproxy` (`windtf/wireproxy` v1.1.3) abre el túnel en espacio de usuario y expone un proxy HTTP,
así que Privoxy sobra. Resultado en la Mac:

- Salida `AS13335 Cloudflare`, MX.
- Captura nacional de Cinépolis completa: 20/20 unidades y 1,094 llamadas, sin `Blocked`.
- 23–26 MB de RSS, estable durante 70 min.
- +0.1–0.2 s por llamada.

Dos corridas salieron hasta 4× más lentas y no se repitió. La prueba instrumentada de CDMX (146 llamadas, 151 s) no tuvo
errores ni reintentos. Falta probar en el servidor que el WAF de Cinépolis acepte esta salida desde AWS: la Mac ya sale
por WARP aunque no use el proxy.

**API pública (`api/`, prueba de carga local, 2026-09-28).** FastAPI + pydantic cuestan ~29 MB fijos: 48 MB contra 19 MB
de `analytics` solo, y 21 MB con `http.server`. La memoria crece con las búsquedas simultáneas, ~13 MB por búsqueda en
curso dentro de `recommend_search`, no con el framework. Diez a veinte usuarios buscaron sin pausa en CDMX, GDL y MTY,
con el límite por IP desactivado:

| Usuarios | Hilos | Peticiones/s | Latencia p50 | RSS pico |
| --- | --- | --- | --- | --- |
| 1 | 40 | 2.9 | 350 ms | 80 MB |
| 10 | 40 | 20.5 | 479 ms | 212 MB |
| 20 | 40 | 22.7 | 866 ms | 311 MB |
| 20 | 8 | 18.3 | 1,125 ms | 181 MB |
| 20 | 4 | 10.5 | 1,701 ms | 142 MB |

Las cifras son de una Mac de 14 núcleos; en el servidor se esperan ~3–4 búsquedas por segundo. Con 2 núcleos, más
hilos solo ocupan memoria, así que conviene limitar la API a 2–4 hilos (el grupo de anyio que usa FastAPI). La caché de
`api/main.py` guarda 64 respuestas: con 120 funciones por pestaña y 6 por cine (2026-09-29) cada una ocupa ~0.3 MB y hasta 0.56 MB
(CDMX a 15 km con combo), ~36 MB en el peor caso. Con el límite de 60
peticiones por minuto por IP, 10 usuarios reales piden a lo más 10 por segundo.

**CPU de ráfaga.** Los `t4g` tienen una línea base del 20 % por vCPU. En modo `unlimited` (el default) lo que pasa de
ahí se cobra; en `standard` la CPU se frena al 20 % al agotar los créditos. Vigilar `CPUCreditBalance` en CloudWatch.

**Orden de trabajo.** Primero `wireproxy` (~700 MB). Luego la captura por unidad (~450 MB). Después, los trabajos pesados
en serie con un candado compartido en `jobs/run.py` y `MemoryMax=` en sus unidades, para que el kernel mate al trabajo y
no al túnel; también el catch-up que provoca el despliegue. Al final, el límite de hilos y la caché de la API. Con más
clientes, separar la captura del servidor que atiende usuarios o volver a `t4g.medium`.

## Red y almacenamiento

- **VPC:** privada (EC2) + Caddy para Streamlit en HTTPS.
- **EBS gp3:** 30 GB, 3,000 IOPS; alcanza ~1 año con la captura nacional sin retención de `event`.
- **Respaldo:** `deploy/backup.sh` diario (05:07): `.backup` de `snapshots.db` y `app.db` comprimidas y el crudo al
  bucket; 7 copias locales. Simulacro en local: 810 MB → 53 MB comprimida en 4 s.
- **Zona horaria:** `America/Mexico_City` en `/etc/timezone` del servidor.

## Configuración recomendada para AWS

| Componente | Especificación | Costo/mes | Notas |
| --- | --- | --- | --- |
| **EC2** | `t4g.medium` (2 vCPU, 4 GB RAM) | ~24.53 USD | `t4g.small` (~12.26 USD) cuando la captura tenga memoria acotada |
| **EBS** | gp3 30 GB | ~2.40 USD | `data/`: bases, crudo y logs |
| **S3** | respaldos + crudo | ~2–5 USD | lifecycle 30 días para `db/` y `app/` |
| **Total** | | ~29–32 USD/mes | — |

## Instalación

```bash
# Desde un t4g.medium en us-east-1 (o tu región)
sudo bash deploy/install.sh
# Variables de entorno en /etc/absolut-cinema.env (ejemplo en deploy/absolut-cinema.env.example)
# Timers arrancados (ver systemctl list-timers)
```
