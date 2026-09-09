# Esquema PostgreSQL: archivo histórico (etapa 1)

Diseño de las tablas de Postgres (RDS o Postgres administrado) que recibirán, vía el trabajo `make sync`, lo que hoy
vive en `data/snapshots.db`. Objetivos: histórico completo consultable con SQL por el cliente, durabilidad y
recuperación a un punto en el tiempo, y un tamaño que aguante la escala nacional. Estado: **propuesta 2026-09-09**,
pendiente de aprobación; el diagrama de despliegue está en `arquitectura-aws.png`. La copia ejecutable del DDL es
`deploy/postgres/schema.sql` (si cambia uno, cambia el otro); para probarlo en local, `make pg-up pg-schema` levanta un
Postgres 16 en Docker (`deploy/docker-compose.dev.yml`).

Principios:

- **Separar identidad de estado.** Lo que no cambia de una función (cine, película, fecha) se escribe una vez; lo que
  cambia (hora, sala, idioma, formato, ocupación) se guarda como versiones con vigencia (`valid_from`, `valid_to`). Así
  "cómo estaba la cartelera el día X a las 13:30" es un `WHERE valid_from <= t AND (valid_to IS NULL OR valid_to > t)`.
- **Tipos nativos.** `timestamptz` para instantes, `date` para fechas, `smallint`/`integer` para conteos y centavos.
  En SQLite todo viaja como texto; la conversión ocurre en el `sync`.
- **Mismo vocabulario que el repo** (`AGENTS.md`): `chain`, `show_id`, `cinema_id`, `screen`, `minutes_to_start`.
- **Append-only donde se pueda.** El `sync` inserta con `ON CONFLICT DO NOTHING`; solo `showtime` y `showtime_state`
  se actualizan (cierre de vigencia). Marca de agua por tabla en `sync_watermark`.
- **El crudo no va a Postgres.** Sigue en S3 (`raw/{chain}/{fecha}/*.json.gz`); `snapshot.raw_path` apunta ahí.

## Tablas

### Captura y catálogo

```sql
CREATE TYPE chain_t AS ENUM ('cinemex', 'cinepolis');

CREATE TABLE snapshot (
  id            integer PRIMARY KEY,            -- mismo id que en SQLite (el sync lo conserva)
  chain         chain_t NOT NULL,
  taken_at      timestamptz NOT NULL,
  finished_at   timestamptz,
  ok            boolean NOT NULL,
  n_shows       integer, n_cinemas smallint, n_events integer, calls integer,
  duration_s    real,
  raw_path      text,                           -- s3://bucket/raw/{chain}/{fecha}/{HHMMSS}Z.json.gz
  error         text
);
CREATE INDEX ON snapshot (chain, taken_at);

CREATE TABLE cinema (                            -- dimensión derivada de las capturas
  chain       chain_t NOT NULL,
  cinema_id   text NOT NULL,                     -- Cinépolis slug, Cinemex id numérico como texto
  name        text NOT NULL,
  lat         double precision, lng double precision,
  city_id     text,                              -- plaza (Cinépolis cityId, Cinemex estado/área); habilita el filtro de zona
  first_seen  timestamptz NOT NULL, last_seen timestamptz NOT NULL,
  PRIMARY KEY (chain, cinema_id)
);

CREATE TABLE movie (
  chain        chain_t NOT NULL,
  movie_id     text NOT NULL,
  title        text NOT NULL, title_norm text NOT NULL,
  genre        text, rating text, duration_min smallint, distributor text,
  first_seen   timestamptz NOT NULL, last_seen timestamptz NOT NULL,
  PRIMARY KEY (chain, movie_id)
);
CREATE INDEX ON movie (title_norm);              -- emparejamiento entre cadenas
```

### Funciones: identidad y versiones

```sql
CREATE TABLE showtime (                          -- una fila por función publicada; el id de Vista se recicla, por eso la fecha va en la llave
  chain          chain_t NOT NULL,
  show_id        text NOT NULL,
  show_date      date NOT NULL,
  cinema_id      text NOT NULL,
  movie_id       text NOT NULL,
  first_seen_at  timestamptz NOT NULL,           -- captura en la que apareció
  closed_at      timestamptz,                    -- captura en la que dejó de estar publicada
  closed_kind    text CHECK (closed_kind IN ('removed', 'expired')),
  PRIMARY KEY (chain, show_id, show_date),
  FOREIGN KEY (chain, cinema_id) REFERENCES cinema (chain, cinema_id),
  FOREIGN KEY (chain, movie_id)  REFERENCES movie (chain, movie_id)
) PARTITION BY RANGE (show_date);                -- particiones mensuales
CREATE INDEX ON showtime (chain, cinema_id, show_date);
CREATE INDEX ON showtime (chain, movie_id, show_date);

CREATE TABLE showtime_state (                    -- versiones del estado mutable (SCD tipo 2)
  chain          chain_t NOT NULL,
  show_id        text NOT NULL,
  show_date      date NOT NULL,
  valid_from     timestamptz NOT NULL,           -- taken_at de la captura que vio este estado por primera vez
  valid_to       timestamptz,                    -- NULL = vigente
  starts_at      timestamp NOT NULL,             -- hora local de la plaza (sin zona: así la publican las cadenas)
  screen         text,
  language       text, language_raw text,
  format         text, experience text, premium_tier text, version_raw text,
  availability   text,                           -- color (Cinépolis) o high/mid/low (Cinemex)
  PRIMARY KEY (chain, show_id, show_date, valid_from),
  FOREIGN KEY (chain, show_id, show_date) REFERENCES showtime
) PARTITION BY RANGE (show_date);
CREATE INDEX ON showtime_state (chain, show_id, show_date, valid_to);
```

Reconstrucción de la cartelera de un cine y un día en el instante `t`:

```sql
SELECT s.*, st.*
FROM showtime s JOIN showtime_state st USING (chain, show_id, show_date)
WHERE s.chain = 'cinepolis' AND s.cinema_id = 'cinepolis-universidad-cdmx' AND s.show_date = '2026-09-10'
  AND s.first_seen_at <= :t AND (s.closed_at IS NULL OR s.closed_at > :t)
  AND st.valid_from <= :t AND (st.valid_to IS NULL OR st.valid_to > :t);
```

### Eventos (auditoría) y muestreos

```sql
CREATE TABLE event (                             -- espejo del diff del scraper; los JSON completos se quedan en SQLite/S3
  id               bigint NOT NULL,              -- id de SQLite
  chain            chain_t NOT NULL,
  show_id          text NOT NULL, show_date date,
  kind             text NOT NULL CHECK (kind IN ('added','removed','expired','moved','changed','availability')),
  detected_at      timestamptz NOT NULL,
  snapshot_id      integer REFERENCES snapshot, prev_snapshot_id integer,
  cinema_id        text, movie_id text,
  changes          jsonb,                        -- solo los campos que cambiaron: {"screen": ["3","5"], ...}
  PRIMARY KEY (id, detected_at)                  -- la llave de una tabla particionada debe incluir la columna de partición
) PARTITION BY RANGE (detected_at);
CREATE INDEX ON event (chain, detected_at);
CREATE INDEX ON event (chain, show_id, show_date);

CREATE TABLE auditorium (                        -- aforo por sala; una fila por medición
  chain chain_t NOT NULL, cinema_id text NOT NULL, screen text NOT NULL,
  sampled_at timestamptz NOT NULL,
  seats smallint NOT NULL, broken smallint NOT NULL, areas jsonb, session_id text,
  PRIMARY KEY (chain, cinema_id, screen, sampled_at)
);

CREATE TABLE occupancy_sample (                  -- plano de asientos leído; minutes_to_start < 0 = tras el inicio (asistencia final)
  id bigint PRIMARY KEY,
  chain chain_t NOT NULL, show_id text NOT NULL, show_date date NOT NULL,
  cinema_id text, screen text, movie_id text,
  starts_at timestamp NOT NULL, sampled_at timestamptz NOT NULL, minutes_to_start smallint NOT NULL,
  seats smallint, sold smallint, broken smallint, sold_pct real, availability text
);
CREATE INDEX ON occupancy_sample (chain, show_date);
CREATE INDEX ON occupancy_sample (chain, cinema_id, show_date);

CREATE TABLE price_sample (                      -- boleto general por cine, cubeta de formato y tipo de día
  id bigint PRIMARY KEY,
  chain chain_t NOT NULL, show_id text NOT NULL, cinema_id text NOT NULL, screen text,
  format_bucket text NOT NULL, day_type text NOT NULL, show_date date NOT NULL, starts_at timestamp,
  sampled_at timestamptz NOT NULL,
  general_cents integer, min_cents integer, max_cents integer, fee_cents integer, tickets jsonb
);
CREATE INDEX ON price_sample (chain, cinema_id, format_bucket, day_type, sampled_at);

CREATE TABLE concession_price (                  -- menú de dulcería en sala (hoy Cinépolis; Cinemex llegará del cliente)
  id bigint PRIMARY KEY,
  chain chain_t NOT NULL, cinema_id text NOT NULL, sampled_at timestamptz NOT NULL,
  category text, sub_category text, product_id text, product_name text NOT NULL,
  price_cents integer NOT NULL, product_structure text, promotion_type text, active boolean
);
CREATE INDEX ON concession_price (chain, cinema_id, sampled_at);
CREATE INDEX ON concession_price (chain, product_name, sampled_at);

CREATE TABLE delivery_price (                    -- dulcería a domicilio (Rappi, DiDi Food)
  id bigint PRIMARY KEY,
  platform text NOT NULL CHECK (platform IN ('rappi', 'didi')),
  chain chain_t NOT NULL, store_id text NOT NULL, store_slug text, store_name text, address text,
  lat double precision, lng double precision, status text, available boolean,
  sampled_at timestamptz NOT NULL,
  category text, product_id text, product_name text NOT NULL, price_cents integer NOT NULL, description text, in_stock boolean
);
CREATE INDEX ON delivery_price (platform, chain, sampled_at);

CREATE TABLE sync_watermark (                    -- hasta dónde llegó el sync por tabla origen
  source_table text PRIMARY KEY, last_id bigint NOT NULL, synced_at timestamptz NOT NULL
);
```

## Mapeo desde SQLite y trabajo `sync`

| SQLite (`scraper/store.py`) | Postgres | Regla del `sync` (cada 15 min, venv propio con `psycopg`) |
| --- | --- | --- |
| `snapshot` | `snapshot` | inserta filas con `id > watermark` |
| `current_showtime` de cada captura | `cinema`, `movie`, `showtime`, `showtime_state` | por cada captura nueva: upsert de cines y películas; `showtime` nuevo si `(chain, show_id, date)` no existe (`first_seen_at`); si el estado mutable difiere de la versión vigente, cierra `valid_to` y abre otra; funciones ausentes se cierran con `closed_at`/`closed_kind` según el evento `removed`/`expired` |
| `event` | `event` | inserta `id > watermark`; `changes` = diferencia de `before_json`/`after_json` sobre los campos rastreados |
| `auditorium` | `auditorium` | inserta si cambió `(seats, broken)` respecto a la última medición de la sala |
| `occupancy_sample`, `price_sample`, `concession_price`, `delivery_price` | mismo nombre | inserta `id > watermark`; `sampled_at`/`detected_at` a `timestamptz`; `datetime_local` a `starts_at` (`timestamp` sin zona) |

El `sync` lee SQLite en `mode=ro` (como `analytics/`), corre en `:22` y `:52` para no coincidir con capturas (`:30`),
butacas (`:50`) ni trabajos diarios (`:07`), y es idempotente: si falla a medias, la siguiente corrida retoma desde la marca
de agua. El scraper no cambia y sigue sin dependencias externas.

## Tamaño estimado

| Tabla | CDMX por año | Nacional (777 cines) por año |
| --- | --- | --- |
| `showtime` (~150 B/fila; ~5,500 funciones nuevas al día en CDMX) | 2.0 M filas · 0.3 GB | 9.5 M filas · 1.4 GB |
| `showtime_state` (una versión por función + ~5 % de cambios) | 2.1 M filas · 0.3 GB | 10 M filas · 1.5 GB |
| `event` sin JSON completos (~200 B; ~2 por función + cambios) | 4.5 M filas · 0.9 GB | 21 M filas · 4.2 GB |
| `occupancy_sample` (post-inicio, censo Cinépolis) | 1.0 M filas · 0.1 GB | 7 M filas · 0.8 GB (o menos si se muestrea) |
| precios, dulcería, aforo | < 0.1 GB | < 0.5 GB |
| **Total aproximado** | **~1.7 GB** | **~8.5 GB** |

Comparado con copiar cada captura completa (83 GB al año a nivel nacional), separar identidad de estado reduce el
archivo unas diez veces y deja la reconstrucción histórica como una consulta directa.

## Etapa 2 (fuera de este documento)

Portar `analytics/` a Postgres: las consultas usan hoy dialecto SQLite (`substr` sobre fechas en texto, `SUM(condición)`);
en Postgres serían `date_part`/`starts_at::time` y `count(*) FILTER (WHERE …)`. Mientras tanto el dashboard sigue
leyendo SQLite y Postgres es solo archivo y acceso del cliente.
