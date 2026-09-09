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
| `current_showtime` | `DELETE` de la cadena + `INSERT` de todas sus filas (`store.py:133`) | 51,468 (Cinemex 28,346 + Cinépolis 23,122) | **308,808** |
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
completo. Por eso `docs/postgres-esquema.md` versiona con `valid_from`/`valid_to` en vez de
reemplazar: el `sync/` del plan 2 no debe replicar el borrado.

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
| `t4g.small` | 2 | 2 GB | 0.0168 USD | ~12.26 USD | ⚠️ Límite mínimo; funciona hoy pero sin margen. Riesgoso con plan 2. |
| **`t4g.medium`** | **2** | **4 GB** | **0.0336 USD** | **~24.53 USD** | ✅ **Recomendado.** 4 GB = seguro en picos + plan 2. |
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
usuario concurrente del dashboard. Con Postgres en RDS (plan 2) sí conviene bajar a `small`.

## Almacenamiento: SQLite vs. PostgreSQL en RDS

### Opción A: SQLite local (hoy, plan 1)
- **Almacenamiento:** EBS gp3 30 GB (~3 años de base + crudo).
- **Overhead en EC2:** SQLite + WAL ≈ 50 MB en pico.
- **Pros:** sin dependencias de red, sin RDS pay-per-use, control local.
- **Contras:** un solo escritor, replicar a otro servidor cuesta, sin búfering entre regiones.
- **Recomendado para:** dev/piloto, si no tienes RDS disponible.

### Opción B: PostgreSQL en RDS + scraper a PostgreSQL (plan 2)
- **BD remota:** RDS `db.t4g.micro` (~11 USD/mes) o `db.t4g.small` (~21 USD/mes).
- **Almacenamiento:** EBS gp3 20 GB en EC2 (crudo + logs, nada de BD).
- **Overhead en EC2:** scraper + Streamlit ≈ 400 MB en pico (sin WAL local).
- **Pros:** escala horizontal, replicación nativa, backup automático AWS.
- **Contras:** latencia de red, costo RDS (+11–21 USD/mes), networking VPC.
- **Recomendado para:** producción en AWS Cinemex, plan 2 en curso.

**→ Con PostgreSQL en RDS, EC2 puede ser `t4g.small` (2 GB, ~12.26 USD/mes).**

## Red y almacenamiento

- **VPC:** privada (EC2) + NLB/Caddy para Streamlit en HTTPS, o pública si confías en basic auth.
- **Seguridad:** EC2 en subnet privada, RDS en subnet privada, HTTPS via Caddy.
- **EBS gp3:** 
  - SQLite (opción A): 30 GB, 3,000 IOPS (~3 años de historia).
  - PostgreSQL (opción B): 20 GB, 3,000 IOPS (solo crudo y logs).
- **Respaldo:** 
  - SQLite: snapshots diarios de EBS a S3 (`backup.timer`).
  - PostgreSQL: automated backups de RDS (retenidos 7–30 días, configurar).
- **Zona horaria:** `America/Mexico_City` en `/etc/timezone` del servidor.

## Configuración recomendada para AWS

### Plan 1 (hoy, SQLite local)
| Componente | Especificación | Costo/mes | Notas |
| --- | --- | --- | --- |
| **EC2** | `t4g.medium` (2 vCPU, 4 GB RAM) | ~24.53 USD | Cubre picos sin swap |
| **EBS** | gp3 30 GB | ~2.40 USD | `/data` → snapshots a S3 |
| **S3** | respaldos gp + crudo | ~2–5 USD | lifecycle 30 días |
| **Total** | | ~29–32 USD/mes | — |

### Plan 2 (con PostgreSQL en RDS)
| Componente | Especificación | Costo/mes | Notas |
| --- | --- | --- | --- |
| **EC2** | `t4g.small` (2 vCPU, 2 GB RAM) | ~12.26 USD | Reduce a 2 GB porque no lleva SQLite WAL |
| **EBS** | gp3 20 GB | ~2 USD | Solo crudo + logs |
| **RDS** | `db.t4g.micro` o `.small` (single-AZ) | ~11–21 USD | Upgradeable, backup automático |
| **S3** | crudo y respaldos | ~2–5 USD | — |
| **Total** | | ~27–41 USD/mes | Escalable, menos operativo |

## Instalación

### SQLite (plan 1)
```bash
# Desde un t4g.medium en us-east-1 (o tu región)
sudo bash deploy/install.sh
# Variables de entorno en deploy/absolut-cinema.env
# Timers arrancados (ver systemctl list-timers)
```

### PostgreSQL (plan 2, próximamente)
```bash
# EC2: t4g.small, en subnet privada
# RDS: db.t4g.micro → db.t4g.small, single-AZ, backup automated
# Variables en deploy/absolut-cinema.env:
#   DATABASE_URL=postgresql://user:pass@rds-endpoint:5432/absolut_cinema
# scraper.run → escribe en RDS via sync/ (conexión TCP)
# analytics/ → lee de RDS (conexión TCP)
```

## Conclusión

**Hoy:** `t4g.medium` (~24.53 USD/mes) cubre todo con margen.  
**Plan 2:** `t4g.small` (~12.26 USD/mes) + RDS (~11–21 USD/mes) escalable, recomendado.

Especifica con el cliente si la BD va en su RDS/AWS o en DigitalOcean para fijar infraestructura.
