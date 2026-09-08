# Cinépolis y Cinemex México: extracción de cines y cartelera

Notas de la investigación sobre https://cinepolis.com/mx y https://cinemex.com para obtener
la lista de cines y su cartelera sin scraping de HTML, y del scraper de snapshots que alimenta
el producto de inteligencia competitiva (Cinemex vs Cinépolis). Fecha: 2026-09-07.

## Resumen

- El sitio de Cinépolis es un **Next.js exportado estáticamente**. El HTML inicial solo trae
  un loader; todo el contenido se pide desde el cliente.
- Los datos vienen de una **API GraphQL pública** en `https://api-g.cinepolis.com`,
  consumida con Apollo. Cada dominio (ubicaciones, cartelera, compra, etc.)
  tiene su propio endpoint.
- La API exige un header `x-apikey`. La key está embebida en el JavaScript del
  sitio y la recibe cualquier visitante, así que no es una credencial privada.
- Ya no hace falta un navegador ni un MCP web: todo se puede pedir con `curl`
  o `urllib`.
- Resultado de la primera fase: `cinepolis_mx_cines.yaml` con **154 ciudades y
  499 cines**, cada uno con el `slug` que el sitio usa en `?cinema=`.
- Segunda fase (2026-09-07): Cinemex también expone una **API REST pública** con clave embebida
  (ver sección "Cinemex"), y quedó corriendo un **scraper de snapshots** cada 15 min para CDMX
  con ambas cadenas (ver "Scraper de snapshots").

## Cómo se encontró

1. `curl` a `https://cinepolis.com/mx?cinema=plaza-acambaro` devolvió un HTML de
   ~5 KB con `__NEXT_DATA__` vacío (`nextExport: true`) y ~20 chunks de
   `/_next/static/chunks/`.
2. El `_buildManifest.js` lista las rutas: `/[country]`, `/[country]/horarios`,
   `/[country]/detalle`, `/[country]/asientos`, `/[country]/pagos`, etc.
3. Concatenando los chunks (~1.4 MB) y buscando URLs aparecieron 25 endpoints
   bajo `api-g.cinepolis.com`, la constante `API_KEY` y los templates `gql`
   completos de cada query (Apollo conserva el texto de la operación).
4. Se probó cada endpoint con la key: los de locations y search responden y
   permiten introspección; el de billboards responde pero tiene la introspección
   deshabilitada, así que sus campos se tomaron de las queries del bundle.
5. Se verificó la cadena completa ciudad → cine → películas → horarios con
   Plaza Acámbaro.

## Autenticación y headers

Todas las peticiones son `POST` con cuerpo JSON `{"query": ..., "variables": ...}`.

```
Content-Type: application/json
x-apikey: lQM6Mkvri1iHksKKCfpAiwGXq0YUZA7Nn6XAXRPr4i13LwXo
country-id: MX
language: ES
```

Sin `x-apikey` la API responde `401 {"message":"Unauthorized access."}`.
El bundle también trae una `API_KEY` que empieza por `AIzaSy…`; es de Google
Maps y no sirve aquí.

## Endpoints

### Relevantes para cartelera

| Endpoint | Introspección | Sirve para |
| --- | --- | --- |
| `/shared-services/locations/graphql` | sí | países, ciudades, cines, códigos postales |
| `/shared-services/search/entities/graphql` | sí | búsqueda libre de cines y películas |
| `/v2/billboards/graphql` | no | películas en cartelera y horarios |

### Otros que existen (no probados)

`/v1/billboards/graphql` (legado), `/shared-services/config/graphql`,
`/shared-services/miscellaneous/graphql`, `/shared-services/orders/graphql`,
`/v1/purchase/graphql`, `/v1/carts/graphql`, `/v1/ticket/graphql`,
`/v1/concessions/graphql`, `/v1/loyalty/graphql`, `/v1/members/graphql`,
`/v1/payment-method/graphql`, `/v1/section/graphql`, `/v1/annual-passes/graphql`.

## Modelo de datos

Los identificadores son **slugs legibles**, no numéricos:

- `cityId` → `acambaro`
- `cinemaId` → `plaza-acambaro` (es el valor de `?cinema=` en la URL del sitio)
- `movieId` → `gungo-y-los-juegos-cavernicolas`

Cada cine tiene además un `vistaId` numérico (ID del sistema Vista de taquilla)
y un `timezone` que la query de horarios pide como parámetro. El `sessionId` de cada función es
el id de sesión de Vista: único por cine, **no** a nivel nacional, y reciclable con el tiempo.

Los nombres de cine **no son únicos**: "Diana Acapulco" aparece dos veces con
slugs distintos (sala tradicional y VIP). Iterar siempre por `slug`.

Tipo `Cinema` (locations): `id, cityId, countryId, vistaId, name, lat, lng,
phone, address, position, featureFlags, cinemaInfo, zipCode, regionId,
experiences, type, distance, businessType, timezone, alias`.

## Queries verificadas

### 1. Ciudades

Endpoint: locations.

```graphql
{ cities(country_id:"MX") { edges { node { id name lat lng timezone } } } }
```

### 2. Cines de una ciudad

Endpoint: locations.

```graphql
{ cinemas(country_id:"MX", city_id:"acambaro") {
    edges { node { id name vistaId timezone businessType lat lng } } } }
```

Variantes disponibles: `cinemasById(country_id, cinemas)` con IDs separados
por coma, `cinemasByCity`, `cinemasByVistaId(countryId, vistaIds)`.

### 3. Búsqueda (atajo para 1 y 2)

Endpoint: search.

```graphql
query Search($countryId: String!, $search: String!) {
  searchEntities(countryId: $countryId, search: $search) {
    edges { node {
      cinemas { id name cityId cityName vistaId timeZone businessType }
      movies { id name } } } } }
```

### 4. Películas en cartelera de un cine

Endpoint: `/v2/billboards/graphql`.

```graphql
query Movies($countryId: String!, $category: String, $cinemas: String, $after: String, $limit: Int) {
  movies(countryId: $countryId, category: $category, cinemas: $cinemas, after: $after, limit: $limit) {
    pageInfo { endCursor hasNextPage }
    totalCount
    edges { node {
      id name originalName distributor rating ratingDescription genre synopsis
      length releaseDate languages formats cities cinemas categories
      experiences { icon name }
      media { resource type code sizes { large medium small } }
      availableForSale
    } } } }
```

Variables de ejemplo:

```json
{"countryId":"MX","category":"now-playing","cinemas":"plaza-acambaro","limit":50}
```

- `category`: `now-playing` (verificado) o `coming-soon` (visto en el bundle).
- `cinemas`: string con **uno o varios slugs separados por coma**, así que se
  puede pedir la cartelera de varios cines en una llamada.
- Paginación por cursor con `after` / `pageInfo.endCursor`.
- URL de póster: `https://tickets-static-content.cinepolis.com` +
  `media.sizes.medium` + `media.resource`.

### 5. Horarios de una película en un cine

Endpoint: `/v2/billboards/graphql`.

```graphql
query Billboard($countryId: String!, $movieId: String!, $cinemas: String!, $timezone: String) {
  billboard(countryId: $countryId, movieId: $movieId, cinemas: $cinemas, timezone: $timezone) {
    dates
    schedules { cinemaId cityId movieId
      dates { date
        languages { language displayLanguage
          showtimes {
            sessionId datetime screen availability isAllocatedSeating
            movieVistaId cinemaVistaId
            format { icon name } experience { icon name }
            alerts { section title message } } } } } } }
```

Variables de ejemplo:

```json
{"countryId":"MX","movieId":"gungo-y-los-juegos-cavernicolas",
 "cinemas":"plaza-acambaro","timezone":"America/Mexico_City"}
```

Respuesta verificada: tres fechas, funciones agrupadas por idioma
(`ESP` / `ESPAÑOL`, `SUB` / `SUBTITULADA`, `ORIGINAL`), cada una con `sessionId`, hora local,
sala y formato. `format.name` vale `2D` o `3D`; `experience.name` vale `XE`, `4DX`, `IMAX`,
`SCREENX`, `XESCREENX`, `SP` (Sala Premium) o `SJ` (Sala Junior). Las salas VIP son cines
aparte con slug `cinepolis-vip-…`.

Existe también `billboardOrderLinking(countryId, movieId, cinemaId,
controlTime, isAbsoluteExperiencePath)` con la misma forma, y `movie(countryId,
id, isAbsoluteMediaPath)` para el detalle de una película; no se probaron.

## Cinemex (Cine 1): API REST

Descubierta el 2026-09-07 con el mismo método (leer el bundle JS del sitio). Cinemex es una SPA
React con chunks en `s3.amazonaws.com/statics3.cinemex.com/v2/static/js/main.*.chunk.js`.

### Autenticación y headers

Todas las peticiones son `GET` a `https://api.cinemex.com/rest/v2.37.2/` y responden JSON.

```
X-API-Consumer-Key: XXQha7vz4kdvoMSdixhN
```

Sin el header, nginx responde `400 Bad Request`. La constante es el `appId` del bundle (`cinemexProd`).
Existen además `https://api-beta.cinemex.com/rest/v2.38/` y `https://api-staging8.cinemex.com/`
(este último con Basic auth). La versión de ruta puede cambiar con un despliegue.

### Endpoints verificados

| Endpoint | Sirve para |
| --- | --- |
| `cinemas/` | 278 cines: `id, name, lat, lng, platinum, area{id,name}, state{id,name}, attributes, status` |
| `cinemas/area/{areaId}` | cines de un área |
| `movies/`, `movies/area/{areaId}` | catálogo: `info.genre, rating, duration ("2h 55m"), distributor, original_title`, `popularity` |
| `cinemas/area/{areaId}/movies/?include_dates=1&initial=1` | cartelera de **todos los cines del área** para el día inicial |
| `cinemas/area/{areaId}/movies/?include_dates=1&date=YYYY-MM-DD` | idem para una fecha |

No existe `cinemas/{id}/movies/` (405): la unidad de consulta es el **área**, no el cine. Otros GET
vistos en el bundle y no probados: `movies/coming/`, `sessions/{id}`, `sessions/now/nearCinema/`,
`states/`, `cinemas/state/{id}`, `landings/page/{slug}/showtimes`.

### Modelo de datos

Los identificadores son **numéricos**. CDMX es `state.id = 8` ("CDMX y Área Metropolitana") con seis
áreas: Centro (15), Nor-oriente (16), Norte (17), Oriente (18), Poniente (19), Sur (20); 87 cines.

Respuesta de cartelera: `{dates: [...30 fechas], cinemas: [{...cine, movies: [{...película,
versions: [{id, label, type, sessions: [...]}]}]}]}`.

- La **versión** lleva idioma y formato: `type` p. ej. `["platinum", "lang_sub"]`, `label`
  "Premium Español", "Platino Subtitulada", "Dolby Atmos Subtitulada". Valores de `type` vistos:
  `traditional, premium, platinum, lang_es, lang_sub, imax, dolby_atmos, confort, jumbo, v3d, v4d`.
  Regla: `lang_sub` = subtitulada; el resto es español (doblada u original en español).
- La **función** (`sessions[]`): `id` (único a nivel nacional; al reprogramar, Cinemex a veces
  reemite la sesión con id nuevo y la misma hora, lo que aparece como `removed` + `added`), `datetime` con offset (`2026-09-07T18:00:00-06:00`),
  `cinema_id`, `movie_id` (de la versión), `parent_movie_id`, `screen_number`, `auditorium_name`,
  `availability` (`high` / `mid` / `low`), `premium`, `extreme`, `seatallocation`, `alerts`.
- `dates` lista 30 días pero solo la semana de cine en curso (jueves→miércoles) trae funciones
  completas; después solo preventas y eventos.

### Costos observados

Área Sur (17 cines, un día): 442 funciones, 1.5 MB, ~8 s. Con `date=` sin cartelera publicada, ~1.5 s.

## Archivos

- `cinepolis_mx_cines.yaml`: 154 ciudades y 499 cines de MX, ordenados
  alfabéticamente sin distinguir acentos. Por cine: `nombre`, `slug`,
  `vista_id`, `timezone`, `lat`, `lng`. Generado con las queries 1 y 2; lat/lng con
  `scripts/add_latlng_yaml.py`.
- `scraper/`: scraper de snapshots de la plaza piloto (CDMX) para ambas cadenas. Ver
  "Scraper de snapshots" abajo.
- `project.md`: este documento.

## Scraper de snapshots (piloto CDMX)

Sin dependencias fuera de la librería estándar. Se ejecuta con `/usr/bin/python3 -m scraper.run`
(opciones `--chain cinepolis|cinemex`, `--no-raw`) y lo lanza launchd cada 15 minutos con
`scraper/com.absolut-cinema.scraper.plist` → `scraper/schedule.sh`. El plist lleva rutas absolutas;
el repo vive en `~/absolut-cinema` porque launchd no puede leer `~/Documents` (protección de
privacidad de macOS, "Operation not permitted"). Si el repo se mueve, regenerar el plist y
recargarlo con `launchctl bootout` + `launchctl bootstrap`.

- `scraper/config.py`: claves (sobreescribibles con `CINEPOLIS_API_KEY`, `CINEMEX_CONSUMER_KEY`,
  `CINEMEX_BASE_URL`), plaza piloto, lotes, horizonte de días.
- `scraper/cinepolis.py`: por lotes de 30 cines pide `movies(now-playing)` y luego `billboard` por
  película. CDMX: 74 cines, ~165 llamadas, 1–2 min. Cada fila lleva el cine en el `show_id`
  (ver "Identidad de la función").
- `scraper/cinemex.py`: por área pide `initial=1` (trae la lista de fechas) y luego cada fecha hasta
  14 días adelante. CDMX: 6 áreas, ~90 llamadas, 1–3.5 min. Recorta sinopsis, pósters y mapas de
  asientos antes de guardar el crudo.
- `scraper/normalize.py`: esquema común por función (`chain, show_id, cinema_id, movie_id,
  title_norm, date, datetime_local, screen, language ∈ spanish|subtitled|original|other,
  format, experience, premium_tier, availability, …`).
- `scraper/store.py`: SQLite en `data/snapshots.db`: `snapshot` (metadatos y errores),
  `current_showtime` (estado vigente por cadena, con `first_seen`), `event` (diff con `before_json`
  / `after_json`). Crudo comprimido en `data/raw/{chain}/{fecha}/{HHMMSS}Z.json.gz`.
- `scraper/diff.py`: compara por `show_id`: `added`, `removed` (solo si faltaban >30 min para
  empezar; si no, expiró), `moved` (hora o sala, misma fecha), `changed` (idioma/formato/película),
  `availability`. Un mismo id que reaparece en otra fecha cuenta como `added`, porque Vista
  recicla ids de sesión.
- Identidad de la función: en Cinemex `sessions[].id` es único a nivel nacional (0 colisiones en
  10,941 funciones). En Cinépolis `sessionId` **solo es único dentro de cada cine** (914 ids
  repetidos entre cines de CDMX en un snapshot), así que `show_id` es `slug-del-cine:sessionId`.
- Logs en `data/logs/run.log` (una línea por cadena y snapshot) y `data/logs/launchd.*`.

Primer snapshot (2026-09-07 ~18:00 CDMX): Cinemex 87 cines / 10,941 funciones; Cinépolis 74 cines /
12,593 funciones. Ambas cadenas publican completa la semana de cine en curso y, más allá, solo
preventas y eventos (Cinépolis llega a listar funciones hasta 5 semanas adelante).

Consultas útiles:

```sql
-- funciones por franja y % subtituladas, hoy
SELECT chain,
       SUM(substr(datetime_local,12,2) < '12')                                        antes_12,
       SUM(substr(datetime_local,12,2) BETWEEN '12' AND '16')                         de_12_a_17,
       SUM(substr(datetime_local,12,2) BETWEEN '17' AND '20')                         de_17_a_21,
       SUM(substr(datetime_local,12,2) >= '21')                                       despues_21,
       ROUND(100.0 * SUM(language = 'subtitled') / COUNT(*), 1)                       pct_sub
FROM current_showtime WHERE date = date('now', 'localtime') GROUP BY chain;

-- últimos cambios detectados
SELECT detected_at, chain, kind, movie_title, cinema_id, datetime_local
FROM event WHERE kind <> 'availability' ORDER BY id DESC LIMIT 50;
```

## Siguiente fase

1. Dejar correr el scraper cada 15 min y revisar `data/logs/run.log` a diario; en especial el
   miércoles/jueves, cuando ambas cadenas publican la semana siguiente.
2. Tabla de equivalencias de películas entre cadenas (`title_norm` + duración + distribuidor, con
   revisión manual de reestrenos, festivales `tcf-`/`cltcf-` y eventos en vivo).
3. Emparejar cines por distancia (lat/lng de ambas fuentes) para la comparación por plaza.
4. Sobre `current_showtime` y `event`: KPIs con deltas, movie battle, huecos horarios, alertas.
5. Con 8–12 semanas de `event`: patrones de hora de publicación por día de la semana.

## Consideraciones

- La key es pública pero puede rotar con cada despliegue del sitio. Si la API
  devuelve 401, volver a extraerla de los chunks de `/_next/static/chunks/`
  buscando `API_KEY:"`.
- Los endpoints de billboards no permiten introspección; si un campo falla,
  quitarlo de la query en vez de adivinar alternativas.
- Mantener un ritmo razonable de peticiones. Toda la lista de cines se obtuvo
  con 155 llamadas secuenciales sin ningún error. Un snapshot completo de CDMX de ambas cadenas
  son ~255 llamadas y 2–5 min; cada 15 min no ha provocado bloqueos ni 429 hasta ahora.
- Cinemex: si responde `400` de nginx en todo, cambió el `X-API-Consumer-Key`; si responde 404 en
  todo, cambió la versión de ruta (`rest/v2.37.2/`). Ambos se releen del `main.*.chunk.js`.
- `availability` de Cinépolis viene vacío en la mayoría de funciones y en algunas trae un color
  (`#FFBE06`, `#FF804A`, `#A2ACBA`), presumiblemente el semáforo de ocupación del sitio. Se guarda
  tal cual; falta confirmar el significado. En Cinemex es `high`/`mid`/`low`.
