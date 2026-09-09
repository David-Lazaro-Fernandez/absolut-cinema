-- Esquema del archivo histórico en PostgreSQL. Copia ejecutable del DDL de docs/postgres-esquema.md:
-- si cambia uno, cambia el otro. Aplicar con `make pg-schema` (local) o `psql -f` contra RDS.
BEGIN;

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

-- Sin particiones por defecto a propósito: si una fila cayera en DEFAULT, crear después la partición mensual de
-- ese rango fallaría. El sync crea showtime_YYYYMM, showtime_state_YYYYMM (por show_date) y event_YYYYMM (por
-- detected_at, límites en UTC) para los meses del lote más el siguiente, antes de insertar.

COMMIT;
