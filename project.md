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
- Tercera fase (2026-09-08): **dashboard ejecutivo** en Streamlit (`app.py` + `analytics/`), archivos
  de despliegue (`deploy/`) y **módulo de muestreo** de aforo por sala, ocupación y precios
  (`scraper/sample.py`, ver "Asientos y precios"). Aforo capturado: Cinépolis 621 salas / 91,330
  butacas; Cinemex 792 salas / 99,889 butacas. Ese mismo día Cinemex cambió el formato de sesión de
  su API (ver "Cambio de payload 2026-09-08").
- Cuarta fase (2026-09-08, tarde): el dashboard pasa a la **jerarquía en tres capas** del mockup de David
  (hallazgos como decisión → evidencia por pregunta → apéndice colapsado + "Qué se desbloquea con tus datos"),
  con paleta nueva (rojo `#E31837`, tinta `#191A1E`, fuente Archivo) y `analytics/findings.py`, que redacta los
  hallazgos a partir de umbrales sobre datos reales (ver "Dashboard ejecutivo").

- Quinta fase (2026-09-09): correcciones del cliente. **Filtro global de franja horaria** (hora de inicio de la
  función, alineado a las franjas de `labels.SLOTS`), **Resumen general** en el formato del reporte diario del cliente
  con los cortes "Todo el día" y "Después de las 6 PM" lado a lado, **historial por función y cartelera "tal como
  estaba"** (evento `expired` en el scraper + `analytics/history.py`), **tres capturas al día**, dulcería de Cinépolis
  por complejo y dulcería a domicilio en Rappi y DiDi Food (ver secciones "Dulcería", "Programación de tareas" y
  "Dashboard ejecutivo").
- Sexta fase (2026-09-10): **acceso por usuario** (login, olvidé mi contraseña con correo por Amazon SES, roles admin y
  consulta), **página de usuarios** para el admin y **explorador de datos** del archivo en Postgres con tablas curadas
  (cines y salas, funciones de la semana, precios). Paquetes nuevos `auth/` y `archive/`, esquema `app` en Postgres
  (ver "Acceso por usuario y explorador de datos").

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
`/v1/purchase/graphql`, `/v1/carts/graphql`, `/v1/ticket/graphql` (**probado el 2026-09-08**: planos
de asientos y boletos, ver "Asientos y precios"), `/v1/concessions/graphql`, `/v1/loyalty/graphql`, `/v1/members/graphql`,
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

No existe `cinemas/{id}/movies/` (405): la unidad de consulta es el **área**, no el cine.
`sessions/{id}` sí existe y trae boletos con precio (ver "Asientos y precios"). Otros GET vistos en el
bundle y no probados: `movies/coming/`, `sessions/now/nearCinema/`, `states/`, `cinemas/state/{id}`,
`landings/page/{slug}/showtimes`. El checkout es `POST buy/selectTickets`, `buy/selectSeats`,
`buy/complete`, etc.

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
- **Cambio de payload 2026-09-08** (entre las 10:21 y las 10:47 CDMX, sin cambio de versión de
  ruta): la sesión del listado de cartelera quedó reducida a `id, datetime, date, timestamp,
  tz_offset, auditorium_number, availability`. Desaparecieron `screen_number`, `auditorium_name`,
  `cinema_id`, `movie_id`, `premium`, `seatallocation`, `alerts`… `auditorium_number` (string) vale lo
  mismo que el viejo `screen_number` (2,000 sesiones comparadas, 100 % coincidencia). Cine, película
  y versión no cambiaron. `normalize.cinemex_rows` lee ambos nombres; `diff.py` ya no cuenta como
  `moved` una sala que pasa de desconocida a conocida. El snapshot 39 generó 16,237 `moved` falsos
  que se borraron a mano. El detalle completo de una sesión sigue en `GET sessions/{id}`.
- `dates` lista 30 días pero solo la semana de cine en curso (jueves→miércoles) trae funciones
  completas; después solo preventas y eventos.
- **Por la tarde-noche cada área deja de listar el día en curso en `dates`** (el 2026-09-07 tres
  áreas lo quitaron alrededor de las 19:00 y las otras tres seguían listándolo a las 19:10), pero
  `date=hoy` sigue devolviendo las funciones pendientes. El scraper pide hoy siempre, aunque no
  venga en `dates`. Antes de ese arreglo el snapshot 14 registró 502 `removed` falsas de ese día
  y el 16 las volvió a dar de alta (1,035 `added`, contando las ya iniciadas que Cinemex conserva
  ~2.5 h). Ambos lotes son artefactos, no cambios reales; limpiarlos con:
  `DELETE FROM event WHERE chain='cinemex' AND date='2026-09-07' AND ((snapshot_id=14 AND kind='removed') OR (snapshot_id=16 AND kind='added'));`

### Costos observados

Área Sur (17 cines, un día): 442 funciones, 1.5 MB, ~8 s. Con `date=` sin cartelera publicada, ~1.5 s.

## Asientos y precios (verificado 2026-09-08)

Qué expone cada API para pasar de funciones a **butacas** (aforo, ocupación) y a **precios**.

### Cinépolis: `/v1/ticket/graphql`, solo lectura, sin sesión de usuario

- `query Seats(countryId, sessionId, cinemaVistaId)` devuelve el plano de la función:
  `seatLayoutData.areas[]{description, areaCategoryCode, rowCount, columnCount, rows[]{physicalName,
  seats[]{id, status, originalStatus, seatStyle}}}` y `maxQuantity`. Valores de `status` vistos:
  `Empty`, `Sold`, `Special` (accesible), `Companion`, `Broken`. Aforo = asientos menos `Broken`;
  vendidos = `Sold`. El `cinemaVistaId` es el `vista_id` de `cinepolis_mx_cines.yaml` y el
  `sessionId` es la parte derecha del `show_id`. Las salas VIP salen con áreas `Tradicional` y
  `LOUNGE` y 35–75 asientos; una tradicional, 101.
- `query Tickets(countryId, sessionId, cinemaVistaId)` devuelve los boletos con `priceInCents` y
  `bookingFee`: Portal San Ángel, tradicional, martes: Admisión general 102.00 + 7.00 de cargo,
  Niños y 3ra edad 81.00, "Que Ofertón" 45.00.
- Calibración del semáforo: dos funciones con `availability = #FFBE06` tenían 32 % y 34 % de
  asientos vendidos; una con `availability` vacío, 0 %. Con el muestreo se puede fijar la escala
  exacta del color.
- `/v1/section/graphql` no tiene `seats`; `/v1/purchase/graphql` no se probó porque `ticket` bastó.

### Cinemex: precios en lectura, plano solo vía checkout

- `GET sessions/{id}` (REST público, mismo header) devuelve por función `tickets[]{name, price
  (centavos), fee, max}`, `screen_number`, `auditorium_name`, `seatallocation`, `availability`
  (`high/mid/low`) y la leyenda de tipos de asiento. Ejemplo: Mundo E Platino, "Platino estreno",
  204.00.
- El plano de asientos **solo** llega como respuesta a `POST buy/selectTickets` con cuerpo
  `{session_id, tickets: [{type: ticket.id, price, qty: 1, extra}]}`. Responde `layout[]` por
  sección con asientos `status` `"E"` hueco, `"0"` disponible, `"1"` vendido, más `transaction_id`
  y `timeout_time`: abre una orden en Vista que caduca sola (no hay endpoint para cerrarla; el
  `/me/sessions/kill` del bundle es de sesiones de usuario). **Decisión 2026-09-08 (David):** en
  fase de desarrollo se acepta abrir estas órdenes para (a) aforo por sala, una vez por sala, y
  (b) calibrar el semáforo `high/mid/low` contra % vendido con ~100 funciones por nivel. La
  ocupación continua de Cinemex sale del semáforo calibrado (`analytics.seats.estimated_occupancy`),
  no del plano; el dato exacto llegará de la taquilla del cliente.

### Módulo de muestreo: `scraper/sample.py` (2026-09-08)

`/usr/bin/python3 -m scraper.sample --capacity | --occupancy | --prices` (`--dry-run`, `--limit`,
`--refresh`, `--lead 60 --tolerance 15`). Tablas nuevas en `data/snapshots.db` (esquema en
`scraper/store.py`):

1. **`auditorium`** (aforo por sala): un plano por (cine, sala) sobre la función futura más próxima,
   probando hasta 3 funciones distintas de la sala si la primera ya no existe (`CAPACITY_CANDIDATES`;
   el snapshot puede listar funciones que la cadena ya retiró, 404 en Cinemex / 101 en Cinépolis);
   `seats` excluye asientos `Broken`, `areas_json` guarda el detalle por área. Pasada inicial el 2026-09-08 sobre 632 salas de CDMX: ~1.7 s por plano, con errores
   transitorios de Vista (`116`, `101305` "inténtalo de nuevo en unos minutos") si se encadenan
   sin pausa, por eso `SAMPLE_PAUSE = 0.6 s` y `SAMPLE_BACKOFF = 5 s` en `config.py`. Las salas
   que fallan no se insertan y se reintentan al volver a correr `--capacity`. Resultado: 621 de 632
   salas (90,951 butacas; salas de 26 a 486 asientos, mediana ~130). Faltan las 8 salas de
   Sentura Tlalnepantla, que responden código `103` de forma persistente (venta en línea caída o
   deshabilitada para ese cine) y 3 salas cuya función elegida caducó (`101`, se resuelve solo).
   Refresco mensual con `--refresh`. Cinemex: misma tabla, pasada `--chain cinemex` (punto 4).
2. **`occupancy_sample`** (ocupación): `--occupancy` toma las funciones de la cadena (Cinépolis por
   defecto) que empiezan
   en [lead−tol, lead+tol] minutos y aún no tienen muestra en esa ventana, pide el plano y guarda
   `seats, sold, broken, sold_pct, minutes_to_start` junto con el `availability` (color) de la
   función para calibrar el semáforo. Lo lanza `scraper/schedule.sh` (y el unit de systemd) justo
   después de cada snapshot, es decir cada 15 min. Para una curva de preventa se puede correr
   además con `--lead 1440` y `--lead 15`.
   **Pase post-inicio (2026-09-08, tarde):** `--post-start` (`--after 20 --tolerance 10`) toma las funciones que
   empezaron hace 10–30 min y guarda el plano con `minutes_to_start` negativo. Es la **asistencia final** y
   el target del modelo de consumo por zona: la prueba del 2026-09-08 sobre 27 funciones mostró que la venta
   sigue creciendo tras el arranque (Zona Cero, Universidad: 3 vendidos a T−60, 18 a +150 min; Coyote, Las
   Antenas: 7 → 18; El Heladero, Ermita: 0 → 8), así que T−60 mide preventa, no consumo. Cinépolis retira la
   función de la cartelera al empezar y deja de estar en `current_showtime`, por eso los candidatos salen de
   la unión de `current_showtime` (Cinemex las conserva ~2.5 h) y de las funciones ya muestreadas a T−60; así
   cada función queda con el par preventa/asistencia. El plano de Cinépolis responde al menos 150 min después
   del inicio; un Spider-Man de 145 min ya no respondía a +146 ("esta función ya no está disponible") mientras
   Coyote (103 min) sí a +151, la regla de corte no está fijada. Corre tras cada snapshot (`schedule.sh`,
   service de systemd). Con `--chain cinemex` usa el checkout, así que no está programado.
3. **`price_sample`** (precios): `--prices` elige una función futura (7 días) por (cadena, cine,
   cubeta de formato, tipo de día) sin muestra en los últimos 7 días y guarda los boletos con
   `general_cents` (adulto regular), `min`, `max` y `fee`. Tipo de día: `weekend` vie–dom, `promo`
   mar–mié (precio reducido en ambas cadenas: Cinemex tradicional a 39.00 el martes 2026-09-08),
   `weekday` lun y jue. Cinépolis vía `Tickets`; Cinemex vía `sessions/{id}`. Sin boletos a la
   venta no se guarda nada y se reintenta. Primera pasada completa 2026-09-08: 494 muestras, 87 cines
   Cinemex y 74 Cinépolis. Lecturas: Cinemex tradicional a **39.00** de lunes a jueves (boleto único
   "Cinemex Manía") y mediana 79 en fin de semana; Cinépolis tradicional 78 en promo y 90–92 el
   resto. Premium: Cinépolis VIP 197 todos los días; Cinemex Platino/Premium 155 promo y 171 resto.
   Gran formato 125–135 Cinemex, 152–154 Cinépolis. Sentura Tlalnepantla salió con "Evento Matinée"
   a 15.00, por eso ahora se excluyen eventos y matinés del muestreo.
4. **Cinemex**: `--capacity --chain cinemex` corrió el 2026-09-08 (David, a mano): **792 de 798
   salas en 87 cines, 99,889 butacas**, salas de 24 a 617 asientos (la de 617 es Ixtapaluca sala 11,
   filas de 30–37 asientos, plausible), promedio 126 frente a 147 de Cinépolis. 1,577 llamadas en
   42 min; las 6 salas restantes tenían sus funciones próximas retiradas y entran con el siguiente
   snapshot. Pendiente la calibración del semáforo
   `--occupancy --chain cinemex --per-level 100 --lead 60 --tolerance 45`, a correr en la tarde-noche
   cuando existen los tres niveles (por la mañana todo es `high`). Ambas usan `buy/selectTickets`;
   las órdenes abiertas caducan solas. Estas llamadas las bloquea el clasificador de la sesión de
   Claude Code, así que se lanzan a mano con el prefijo `!`.
   Con el aforo de ambas cadenas, butacas ofertadas hoy y mañana (2026-09-08/09): Cinemex 835,931
   (127 por función), Cinépolis 704,557 (148 por función): Cinemex da más funciones en salas más
   chicas, y la ventaja en funciones por cine se reduce al medirla en butacas.
5. Logs en `data/logs/sample.log`. Cubeta de formato: `normalize.format_bucket` (misma regla que el
   `CASE` de `analytics/queries.py`). El muestreo de precios excluye eventos y matinés.

## Dulcería (2026-09-08/09)

Petición del cliente tras la primera revisión: entender los precios de dulcería de Cinépolis.

- **Cinépolis: resuelto.** La página `/mx/solo-alimentos?cinema=…` carga un microfrontend aparte
  (`foods-menu-mf.cinepolis.com`, module federation; el bundle principal solo trae `HasConcessions`). Ese MF consulta
  `https://api-g.cinepolis.com/v1/fab-struct-concession/graphql` con la misma `x-apikey`, query `MenuByType(country,
  cinema, menuType, userSession)`: `cinema` es el **vistaId**, `menuType` no cambia la respuesta (probado con seis valores)
  y `userSession` acepta cualquier UUID. Devuelve categorías → productos con `price` en centavos, `productStructure`
  (`simple`, `compound` con tamaños como modificadores, `combo`) y `promotionType`. Endpoints hermanos vistos en el MF:
  `v1/fab-struct-product/graphql` (`BatchProducts`, `ProductsBatch`: detalle y modificadores) y `v1/fab-promotion/graphql`
  (`ValidVoucher`). Introspección deshabilitada en todos.
- Pase `scraper.sample --concessions` (tabla `concession_price`, un menú completo por cine cada 7 días; corre en `daily.sh`
  y en `prices.service`). Primera pasada 2026-09-09: 74 cines, 10,942 referencias, 340 productos distintos, 92 s.
- **Hallazgo:** Cinépolis fija el precio **por complejo**: palomitas base de 86 a 107 (7 precios distintos en 74 cines),
  refresco 79–110, Combo Clásico 222–322, Maxicombo Nachos 342–472; los VIP arriba. `analytics/concessions.py` expone la
  canasta comparable (`BASKET`, nombres exactos de Clásicos/Combos), el precio de un producto por complejo, la canasta
  pivotada por complejo y las categorías; apéndice "Dulcería de Cinépolis: precio por complejo" en el dashboard.
- **Cinemex: no expuesto.** `GET candybar/catalog?cinema_id=|session_id=` existe pero devuelve `catalog: []` porque el flag
  `candybar` es `false` en los 278 cines de `cinemas/` (venta en línea apagada). El cliente entregará sus precios. Fuentes alternativas
  investigadas el 2026-09-09 en `docs/dulceria-cinemex-fuentes.md`: Cinemex vende dulcería en Uber Eats, Rappi y DiDi
  Food con ~20 SKUs a **precio nacional** (idéntico en 15 sucursales; Combo Tradicional 150, Mega Palomitas 104, Hot Dog
  58, lata 29), catálogo "para llevar" que no refleja el tablero de sala; Uber Eats prohíbe scraping en sus términos,
  DiDi Food es la opción de menor riesgo. No hay fuente pública del tablero de sala por cine.
- **Delivery capturado (2026-09-09):** `scraper/delivery.py` (`make delivery`, diario 15:00 con las tiendas abiertas, cada
  tienda renovada a los 7 días; tabla `delivery_price`) lee Rappi (`__NEXT_DATA__`; tiendas por marca:
  Cinemex 51760, Cinépolis Tradicional 96681; el sitio redirige con 308 al slug canónico, que `http.py` sigue) y
  DiDi Food (HTML estático; las tiendas de cines están en la categoría `pasaboca`, paginada). Descubiertas 229
  tiendas en CDMX: Rappi 35 Cinemex y 70 Cinépolis, DiDi 36 Cinemex y 77 Cinépolis. `analytics/delivery.py`
  compara por cubetas de producto (`DELIVERY_BUCKETS`) porque los nombres difieren entre cadenas; apéndice
  "Dulcería a domicilio" en el dashboard. Lectura del 2026-09-09: Cinemex precio único nacional (95 % de los
  productos con un solo precio); combo básico 150 vs 208 en Cinépolis, nachos 65 vs 120, refresco 29 (lata) vs
  44 (600 ml).

## Archivos

- `cinepolis_mx_cines.yaml`: 154 ciudades y 499 cines de MX, ordenados
  alfabéticamente sin distinguir acentos. Por cine: `nombre`, `slug`,
  `vista_id`, `timezone`, `lat`, `lng`. Generado con las queries 1 y 2; lat/lng con
  `scripts/add_latlng_yaml.py`.
- `scraper/`: scraper de snapshots de la plaza piloto (CDMX) para ambas cadenas. Ver
  "Scraper de snapshots" abajo.
- `analytics/`: consultas de negocio sobre `data/snapshots.db` (`concessions.py`: dulcería). Funciones puras que reciben una
  conexión de solo lectura y una **ventana de fechas** `(d0, d1)` y devuelven listas de dicts; sin
  dependencias. `queries.py` (`kpis`, `showtimes_by_slot`, `heatmap_day_slot`, `movies_by_chain`,
  `mix`, `concentration`, `coverage`, `recent_events`, `events_by_kind`, `snapshot_health`,
  `cinema_week`), `findings.py` (Capa 1: hasta tres hallazgos redactados como decisión con sus números de
  soporte, y las conclusiones que abren cada sección de la Capa 2; cada hallazgo entra solo si cruza su umbral
  en pp), `headlines.py` (frases ejecutivas por tema, versión previa; la app ya no lo usa pero sigue exportado)
  y `labels.py` (todo texto de cara al usuario: franjas, cubetas de formato, tipos de cambio, colores). Toda la lógica de negocio va
  aquí para que un API (FastAPI) pueda exponer lo mismo después sin reescribir.
- `app.py`: entrada del dashboard Streamlit (configuración, CSS, `st.navigation` con las páginas `views/cartelera.py`
  y `views/dulceria.py`; helpers compartidos en `ui/common.py`, 2026-09-09), en la raíz del repo para que Streamlit recargue
  también `analytics/` al editarlo. Dependencias en `requirements-dashboard.txt` (venv `.venv/`,
  Python 3.12; gráficas con Altair, que viene con Streamlit; `watchdog` para que la recarga en
  caliente detecte cambios en módulos importados). Si aparece un `ImportError` de un nombre que sí
  existe en `analytics/`, es el proceso viejo con módulos en memoria: reiniciar Streamlit.
  `analytics/seats.py` cubre aforo, butacas ofertadas, ocupación muestreada, calibración del
  semáforo y precios.
- `deploy/`: units de systemd (cartelera 3/día, planos cada hora, diarios, dashboard, respaldo), `backup.sh`,
  `Caddyfile` e `install.sh` para un droplet o EC2. Ver `deploy/README.md`.
- `ARCHITECTURE.md`: diagramas Mermaid del flujo de datos, la programación de servicios y el catálogo de
  servicios con su cadencia y sus tablas.
- `docs/postgres-esquema.md`: diseño de tablas de PostgreSQL para el archivo histórico (etapa 1, propuesta 2026-09-09):
  identidad de la función separada de sus versiones de estado, eventos, muestreos, trabajo `sync` y tamaño estimado.
  `docs/arquitectura_aws.py` genera el diagrama de despliegue (`arquitectura-aws.png`) con la librería `diagrams`.
- `docs/ec2-sizing.md`: qué instancia EC2 pide el proyecto, con el consumo de cada trabajo, el volumen de
  escritura medido y el crecimiento en disco (2026-09-09).
- `docs/aws-setup.md`: provisión en AWS paso a paso (VPC, grupos de seguridad, rol de IAM, RDS, EC2, S3,
  secretos y monitoreo) para el plan 1 con SQLite y el plan 2 con PostgreSQL.
- `project.md`: este documento.

## Scraper de snapshots (piloto CDMX)

Sin dependencias fuera de la librería estándar. Se ejecuta con `/usr/bin/python3 -m scraper.run`
(opciones `--chain cinepolis|cinemex`, `--no-raw`) y lo lanza launchd tres veces al día con
`scraper/com.absolut-cinema.scraper.plist` (`make snapshot`). El plist lleva rutas absolutas;
el repo vive en `~/absolut-cinema` porque launchd no puede leer `~/Documents` (protección de
privacidad de macOS, "Operation not permitted"). Si el repo se mueve, regenerar el plist y
recargarlo con `launchctl bootout` + `launchctl bootstrap`.

- `scraper/config.py`: claves (sobreescribibles con `CINEPOLIS_API_KEY`, `CINEMEX_CONSUMER_KEY`,
  `CINEMEX_BASE_URL`), plaza piloto, lotes, horizonte de días.
- `scraper/cinepolis.py`: por lotes de 30 cines pide `movies(now-playing)` y luego `billboard` por
  película. CDMX: 74 cines, ~165–172 llamadas, 1–2 min con solo la semana en curso publicada y
  **6–7 min** en cuanto publican la siguiente (mismas llamadas, más fechas por respuesta). Cada fila
  lleva el cine en el `show_id` (ver "Identidad de la función").
- `scraper/cinemex.py`: por área pide `initial=1` (trae la lista de fechas) y luego cada fecha hasta
  14 días adelante. CDMX: 6 áreas, ~90 llamadas, 1–3.5 min. Recorta sinopsis, pósters y mapas de
  asientos antes de guardar el crudo.
- `scraper/normalize.py`: esquema común por función (`chain, show_id, cinema_id, movie_id,
  title_norm, date, datetime_local, screen, language ∈ spanish|subtitled|original|other,
  format, experience, premium_tier, availability, …`).
- `scraper/store.py`: SQLite en `data/snapshots.db`: `snapshot` (metadatos y errores),
  `current_showtime` (estado vigente por cadena, con `first_seen`), `event` (diff con `before_json`
  / `after_json`), más `auditorium`, `occupancy_sample` y `price_sample` del muestreo. Crudo
  comprimido en `data/raw/{chain}/{fecha}/{HHMMSS}Z.json.gz`.
- `scraper/http.py`: reintenta 429, 408 (Cinépolis: "downstream duration timeout" del gateway, visto
  el 2026-09-08) y 5xx con espera progresiva.
- Programación: los plists de `scraper/` y los units de `deploy/` ejecutan targets de `make`
  (`snapshot`, `seats`, `daily`, `delivery`). Ver "Programación de tareas".
- `scraper/diff.py`: compara por `show_id`: `added`, `removed` (solo si faltaban >30 min para empezar),
  `expired` (desapareció porque ya empezó o estaba por empezar; desde el 2026-09-09 deja evento con la fila
  completa y su `first_seen`, para poder reconstruir la cartelera de un día pasado: sin él las funciones
  concluidas no dejaban rastro fuera del crudo), `moved` (hora o sala, misma fecha), `changed`
  (idioma/formato/película), `availability`. Un mismo id que reaparece en otra fecha cierra la anterior y
  cuenta como `added`, porque Vista recicla ids de sesión. `expired` no aparece como cambio en el dashboard.
  Volumen: ~6–7 mil eventos al día (~4 MB).
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

## Programación de tareas (2026-09-08)

Cada unidad de launchd (Mac) y de systemd (servidor, `deploy/`) ejecuta **un target de `make`**, así cualquier
cosa automática se reproduce a mano igual (`make help`). Se descartó Grunt: es un task runner de Node para builds
de JavaScript y el proyecto es Python sin front end compilado.

**Decisión del cliente (2026-09-08, aplicada 2026-09-09): la cartelera se captura tres veces al día**, a las
07:30, 13:30 y 20:30 CDMX (`config.SNAPSHOT_HOURS`). **Los planos de asientos van cada hora y solo post-inicio**
(decisión 2026-09-09): el plano existe ~2.5 h tras el inicio, así que una corrida por hora con ventana de 15 a 75 min cubre
todas las funciones; la lectura de preventa a T−60 se dejó de programar porque el 59 % de sus lecturas era cero y la
asistencia final es lo que vale (target del modelo de consumo). Los cambios del competidor se leen como comportamiento
semanal, no como alerta: el apéndice de cambios muestra 7 días y ya no cuenta la ocupación como cambio. Costos aceptados: una cancelación entre capturas de una función que ya habría empezado
en la siguiente se registra como `expired`, no `removed`; el semáforo de Cinemex se refresca tres veces al día; la
publicación de la semana siguiente se detecta con hasta 6 h de retraso. Una cuarta captura a las 23:30 reduciría lo
primero si hiciera falta.

| Trabajo (`make …`) | Cadencia | Mac (launchd) | Servidor (systemd) |
| --- | --- | --- | --- |
| `snapshot`: captura de cartelera | 07:30, 13:30, 20:30 | `com.absolut-cinema.scraper` | `absolut-cinema-scraper.timer` |
| `seats`: planos post-inicio (asistencia final) | cada hora, :50 | `com.absolut-cinema.seats` | `absolut-cinema-seats.timer` |
| `daily`: salud + precios + dulcería Cinépolis | diario 06:00 | `com.absolut-cinema.daily` | `health.timer` 08:07 y `prices.timer` 06:07 |
| `delivery`: dulcería a domicilio (Rappi, DiDi Food) | diario 15:00 (tiendas abiertas) | `com.absolut-cinema.delivery` | `delivery.timer` 15:07 |
| `capacity REFRESH=1`: aforo Cinépolis | mensual | a mano | `capacity.timer` día 1 04:07 |
| `calibrate-cinemex` | diario 19:07 | a mano (`!`) | `calibrate-cinemex.timer`, enlazado pero apagado (abre órdenes de checkout; tope 60 por corrida) |
| `backup` | diario 05:07 | no aplica | `backup.timer` |
| Pipeline `geo/` (arquetipos de zona) | trimestral | a mano | no aplica |

`scraper/health.py` (`make health`) revisa por cadena la edad de la última captura (umbral 12 h: el hueco nocturno
normal es de 11 h), que cada captura programada de la ventana tenga un snapshot bueno a ±30 min, capturas
fallidas, muestras de ocupación T−60 y post-inicio, precios de 7 días y que los pases semanales de dulcería no
lleven más de 8 días sin renovarse; escribe una línea en `data/logs/health.log` y sale con 1 si hay problemas
(así el timer queda como fallido en `systemctl list-timers`). Los timers diarios van a :07 y `store.connect` tiene
`timeout=60` para convivir con una captura en curso (SQLite en WAL, un escritor a la vez). Hay pruebas unitarias
para la lógica pura (`tests/`, pytest en el venv, `requirements-dev.txt`).

## Front end y hosting (decisión 2026-09-07; servidor fijado el 2026-09-09)

- **Streamlit para el piloto**, con la lógica en `analytics/` y no en las páginas. FastAPI + Next.js
  queda para cuando haya login por usuario de Cinemex, UI con marca, más de un consumidor de los
  datos (alertas, etc.) o más de cinco o seis pantallas. Con `analytics/` separado, el cambio es
  envolver cada función en un endpoint.
- **Servidor: EC2 en la cuenta de AWS de Cinemex** (decisión de David, 2026-09-09; queda descartado el
  droplet de DigitalOcean). Instancia `t4g.medium` (ARM Graviton2, 2 vCPU, 4 GB) con 30 GB de EBS gp3,
  ~29–32 USD al mes con el respaldo en S3. **Cinépolis no acepta la IP de AWS** (su WAF de Cloudflare bloquea el ASN,
  descubierto en el primer despliegue el 2026-09-10): las llamadas a `api-g.cinepolis.com` salen por el cliente WARP de
  Cloudflare instalado en la instancia, en modo proxy y con Privoxy como puente HTTP; Cinemex y el resto salen directo.
  Es un servicio más del host, lo instala `install.sh` y no cambia la instancia ni la red de AWS (no hace falta NAT ni
  IP elástica para esto). Ver "Consideraciones" y `deploy/README.md`. Con el archivo histórico en RDS (plan 2) la instancia puede
  bajar a `t4g.small`, porque deja de llevar el WAL de SQLite. Dimensionamiento en `docs/ec2-sizing.md`
  y provisión paso a paso en `docs/aws-setup.md`.
  Lo urgente es salir de la Mac: launchd deja huecos en la serie cada vez
  que la laptop duerme (la noche del 7 al 8 de septiembre se perdieron ~8 h de snapshots por eso).
  Zona horaria del servidor en `America/Mexico_City`. SQLite ya está en WAL; el dashboard abre la
  base en modo lectura.

### Volumen de escritura y crecimiento (medido el 2026-09-09)

Contado sobre `data/snapshots.db` con la historia desde el 2026-09-07, no estimado. Con la cadencia de
tres capturas al día se escriben **~320,000 filas al día**, de las cuales **el 96 % es el `DELETE` de la
cadena y el `INSERT` de sus 51,468 funciones vigentes** que hace `store.replace_current` en cada captura
(Cinemex 28,346 y Cinépolis 23,122). La información nueva de verdad son ~11,600 filas: ~7,000 eventos,
~1,750 muestras de ocupación, ~1,563 precios de dulcería, ~968 de dulcería a domicilio y el resto entre
precios de boleto, aforo y metadatos de captura.

En SQLite ese reemplazo es una transacción local y no cuesta nada. Importa para el plan 2: replicarlo en
Postgres dejaría 308,808 tuplas muertas al día para autovacuum, y por eso `showtime_state` versiona con
`valid_from`/`valid_to` en vez de reescribir el estado entero.

Crecimiento en disco: la base sube ~7 MB al día (~2.5 GB al año) y el crudo comprimido ~2 MB al día
(~0.7 GB al año, 0.65 MB por corrida). `current_showtime` no crece porque se reemplaza; lo que crece sin
límite es `event` (883 B por fila, ~980 B con sus tres índices). Al pasar a Postgres el mismo año de CDMX ocupa ~1.7 GB
porque separa identidad de estado y no guarda los JSON completos (ver `docs/postgres-esquema.md`).

## Dashboard ejecutivo (estructura en tres capas, 2026-09-08)

Sigue el mockup "Cartelera CDMX — Propuesta de jerarquía en 3 capas" (HTML de David, 2026-09-08), que a su vez
hereda del brief "Dashboard ejecutivo de inteligencia de programación": todo se compara en **share de la
programación de cada cadena** (Cinemex tiene 87 cines y Cinépolis 74 en CDMX), las diferencias entre
porcentajes van en **puntos porcentuales**, la unidad de análisis es la **semana de cine** (jueves a
miércoles) y para el día en curso solo se cuentan funciones que no han empezado. Paleta y tipografía en
`DESIGN.md`: Cinemex rojo `#E31837`, Cinépolis tinta `#191A1E`, fuente Archivo.

Decisión clave: **datos reales, nunca sintéticos**. Lo que no existe no se muestra con cifras; los paneles
pendientes viven como argumento en el bloque "Qué se desbloquea con tus datos".

### Capa 1 · Lo que importa hoy (`analytics/findings.py`)

Hasta tres tarjetas (titular como decisión, una línea de contexto, chip "Decisión: …", cuatro a seis números
de soporte). Se evalúan en este orden y entran solo si cruzan su umbral:

| Hallazgo | Umbral | Qué compara |
| --- | --- | --- |
| Título por butacas | ≥ 1.5 pp entre Δ funciones y Δ butacas | el título compartido donde la apuesta por sala cuenta otra historia que la apuesta por funciones (cuatro redacciones: invertida, amplificada, diluida, en cada dirección) |
| Concentración | ≥ 3 pp en el peso del Top 3 | quién concentra la parrilla y cuántos títulos exclusivos cubre el otro |
| Dulcería | ≥ 10 % de brecha mediana en la canasta comparable a domicilio | quién cobra más a domicilio y el modelo de precio en sala (por complejo vs lista única); va tercero porque es información de valor directo para el cliente |
| Franjas | ≥ 1 pp en la franja con mayor Δ | dónde nos ganan o ganamos, con el pico de cada cadena y, si el periodo tiene dos días, el Δ por día |
| Formato | ≥ 5 pp en Premium/VIP, Gran formato o 3D-4D | la diferencia estructural de sala, más quién subtitula más |
| Exclusivas | ≥ 3 títulos de Cinépolis con ≥ 20 funciones | qué exhiben que no tenemos |

Si ninguna diferencia cruza su umbral, la capa lo dice. Con el periodo "resto de la semana" del 2026-09-08
salieron: Coyote (apuesta amplificada en butacas, +7.8 pp), concentración (47 % vs 40 % del Top 3) y la noche
(Cinépolis pone 2.6 pp más después de las 9 PM).

### Filtro global de franja horaria (2026-09-09)

En la barra lateral, bajo el periodo: presets "Todo el día", "Después de las 6 PM", "Matiné, antes de las 12 PM" o
un rango libre que solo corta en los límites de las franjas (`labels.HOUR_MARKS`, para no partir ninguna). Entra por
`hours=(h0, h1)` (h1 exclusiva) en `queries._window`, el único punto donde se filtra por fecha, y lo heredan las nueve
consultas de ventana, `findings` y `conclusions`. Con `hours=None` o `(0, 24)` la SQL es idéntica a la de antes.
Semántica: las participaciones se calculan **dentro** de la franja; por eso con filtro activo se omite el hallazgo de
franjas, la fila prime/evening de los indicadores y el mapa de calor solo muestra las franjas incluidas. El encabezado
y el pie dicen qué franja está activa. El Resumen general no obedece este filtro: muestra sus dos cortes lado a lado.

### Capa 2 · Evidencia por pregunta

Cuatro secciones blancas; cada una abre con la conclusión (`analytics.conclusions`) y cierra con "Cómo leerla"
colapsado:

0. **¿Cómo se reparte la programación de la semana?** (2026-09-09) La tabla del reporte diario del cliente
   (`analytics/summary.py::general_summary`): Top 11 películas + Resto + Total, por cadena cines, funciones y % de la
   programación, Δ funciones (Cinemex − Cinépolis), Δ pp y la razón Cinépolis/Cinemex, en dos pestañas "Todo el día"
   y "Después de las 6 PM". Alcance CDMX y semana de cine, así que no coincide con la tabla nacional por semana ISO
   del cliente; se dice en "Cómo leerla". Las diferencias van en tinta, no en rojo/verde (el rojo es Cinemex).
1. **¿A qué películas les damos más pantalla?** Dumbbell de share por película con Δ pp; muestra las 8 de mayor
   diferencia entre las 15 más programadas y un interruptor para ver las 15.
2. **¿Estamos en el horario donde vive la taquilla?** Mapa de calor día × franja con Δ pp (rojo: Cinemex pone
   más; tinta: Cinépolis), sin leyenda de color porque el número va en la celda.
3. **¿Con qué formatos e idiomas competimos?** Barras al 100 % de formato (Premium/VIP, Gran formato, 3D o 4D,
   Tradicional) e idioma.
4. **¿Cómo compite nuestra dulcería con la de Cinépolis?** (2026-09-09, a petición de David: la dulcería es un módulo
   propio, no un apéndice, porque es información de valor para el cliente; vive en la página "Dulcería".) Barras pareadas Cinemex vs Cinépolis por
   tipo de producto a domicilio (Rappi, DiDi Food, misma plataforma) con selector de plataforma; barras del precio en
   sala de Cinépolis por complejo con selector de producto (muestra los niveles de precio); detalle colapsado con la
   canasta por complejo, el catálogo y las tiendas. Hallazgo de Capa 1 `dulceria` si la brecha mediana de la canasta
   comparable a domicilio cruza `CONCESSION_MIN_PCT` (10 %); conclusión `dulceria` en `analytics.conclusions`.

### Capa 3 · Detalle y apéndice

Expanders con una línea de resumen en gris al lado del título, para que no haga falta abrirlos:

| Apéndice | Resumen visible | Contenido |
| --- | --- | --- |
| Indicadores del periodo | funciones por cine y día, butacas ofertadas | el antiguo KPI strip como tabla Cinemex / Cinépolis / Δ, más HHI, Top 3 y títulos por complejo |
| ¿Cómo ha movido Cinépolis su cartelera esta semana? | canceladas y cambios de horario por cadena en 7 días | comportamiento semanal del competidor: tabla por tipo de cambio (sin ocupación), glosario y registro por función |
| Precio del boleto por formato y tipo de día | rango de sobreprecio de Cinépolis y dos pares clave | tabla mediana Cinemex / Cinépolis / Δ % y detalle de muestras |
| Salas y butacas por complejo | salas, butacas y sala típica de cada cadena | tabla por cadena, selector de cadena, funciones vs butacas por película y tabla por complejo |
| Ocupación medida tras el inicio | funciones medidas, % vendido, estado de la calibración | calibración por color (Cinépolis), semáforo de Cinemex y últimas muestras |
| Historial de una función y cartelera tal como estaba | historia desde la primera captura | cadena → cine → fecha → sala → función; línea de tiempo (publicada, cambios, cierre) y slider de capturas que reconstruye la cartelera de la sala (`analytics/history.py`) |

**Historia (2026-09-09).** `analytics/history.py`: `functions_on` (vigentes ∪ cerradas por `removed`/`expired`),
`showtime_timeline` (eventos con los campos cambiados; el primer elemento es la publicación, `first_seen`),
`board_as_of` (replay inverso desde `current_showtime`: quita altas posteriores, restaura cierres, revierte cambios) y
`snapshot_times`. Verificado el 2026-09-09 contra el crudo gz de dos capturas: 23,651 y 23,607 funciones de Cinépolis,
0 discrepancias. Es exacta desde que existe el evento `expired`; para fechas anteriores las funciones concluidas no
están (p. ej. el 8 de septiembre en Ajusco aparece vacío).

Cierra el bloque oscuro **"Qué se desbloquea con tus datos"**: taquilla por título → abrir/mantener/recortar;
preventa batch → curva vs comparables; taquilla por función → ingreso real vs potencial; pasada manual →
ocupación estimada de Cinemex (desaparece al calibrar el semáforo); automático 24 sep → decaimiento;
automático 5 oct → tendencia de 4 semanas; captura → geografía por alcaldía.

### Implementación

**Páginas (2026-09-09, a petición de David):** `st.navigation(position="top")` con "Cartelera" (tres capas y los
filtros de periodo y franja en la barra lateral) y "Dulcería" (página propia: hallazgo, precio en sala por complejo y
comparación a domicilio; no depende del periodo). En celular el CSS fija la barra de navegación abajo. La Capa 1 de la
cartelera enlaza a la página de dulcería cuando su hallazgo cruza el umbral.

`ui/common.py` pinta HTML propio (`st.markdown(unsafe_allow_html=True)`) para encabezado, rótulos de capa, tarjetas
de hallazgo, conclusiones, tablas compactas y el bloque de desbloqueo; los gráficos son Altair con el estilo
común de `chart()`; secciones y apéndices son contenedores con `key` (`sec-*`, `apendice-*`, `leerla-*`) que
el CSS estiliza. Cuidados aprendidos: no forzar `font-family` sobre `[class*="st-"]` (rompe los iconos
Material de los expanders); escapar `$` en etiquetas de expander (Streamlit lo lee como LaTeX); las
gráficas llevan `background=PAPER` porque el fondo de página es gris; la barra lateral conserva periodo,
zona y glosario. Al cambiar `analytics/labels.py` o `.streamlit/config.toml` hay que reiniciar Streamlit.

Cubetas de formato (en SQL, `analytics/queries.py`): Premium/VIP = `premium_tier` premium, platinum,
vip o experiencia Confort / SP; Gran formato = IMAX, XE, ScreenX, XEScreenX, Dolby Atmos, Jumbo,
LED; 3D o 4D = formato 3D o 4DX / v4d; el resto Tradicional. Idioma: subtitulada vs español
(doblada u original). Horario prime: viernes a domingo desde las 6:00 P.M.

## Estado al 2026-09-09 y siguiente fase

**Qué corre hoy (Mac, launchd; en el servidor EC2 desde el 2026-09-10 con `deploy/`, Cinépolis vía WARP):** captura de cartelera de CDMX tres veces al día
(07:30, 13:30, 20:30), planos de asientos post-inicio de Cinépolis cada hora, precios de boleto y menú de dulcería de
Cinépolis a diario, dulcería a domicilio (Rappi, DiDi Food) a diario, salud de la captura a diario. Todo escribe solo en
`data/snapshots.db`; el dashboard (dos páginas: cartelera y dulcería) la lee en modo solo lectura.

**Qué tiene el dashboard:** hallazgos con umbral (título, concentración, dulcería, franjas, formato, exclusivas),
Resumen general en el formato del cliente con los cortes "Todo el día" y "Después de las 6 PM", filtro global de franja
horaria, dumbbell por película, mapa de calor, formatos e idioma, módulo de dulcería (sala y domicilio), apéndices de
indicadores, comportamiento semanal del competidor, precios, salas y butacas, historial por función con cartelera "tal
como estaba", y ocupación medida.

**Archivo histórico en PostgreSQL (etapa 1, construido el 2026-09-09):** `sync/` (`make sync`, launchd y systemd a :22 y
:52) copia lo nuevo de SQLite por marca de agua y reconstruye la historia de cada función desde el crudo de cada captura
como identidad (`showtime`) + versiones de estado (`showtime_state`, `valid_from`/`valid_to`), con las mismas reglas del diff
del scraper (`scraper.diff.changed_fields`, `closing_kind`, `normalize.TRACKED_FIELDS`). Carga inicial: 79 capturas,
62,499 funciones, 2,480 con más de una versión, en 30 s; verificado contra SQLite (0 diferencias en el estado vigente),
contra el crudo (misma cantidad de funciones distintas; la reconstrucción "tal como estaba" coincide en dos capturas
intermedias) y en eventos (mismos ids). Destino hoy: Postgres 16 en Docker local (`make pg-up pg-schema`); RDS después
cambiando `AC_PG_DSN`. Diseño en `docs/postgres-esquema.md`, operación en `deploy/README.md`.

**Decisiones abiertas con el cliente:** alcance nacional (hoy solo CDMX; multiplica ~7× las llamadas y exige muestrear
los planos en vez de censarlos), entrega de su tablero de dulcería y de su taquilla por función, si el entregable vive en
su cuenta de AWS (RDS) o en DigitalOcean.

### Etapa 1 del archivo histórico: hecha (2026-09-09)

Decisiones de diseño que quedaron: el crudo es la fuente de la historia (no `current_showtime`); una función cerrada que
reaparece con la misma llave se reabre (479 casos en dos días); un cambio de película o cine corrige la identidad; un
snapshot sin cerrar más viejo de 2 h se copia como fallido; Postgres es append-only (los borrados manuales de eventos en
SQLite no se propagan); particiones mensuales bajo demanda, sin DEFAULT; `cinema.city_id` sale del crudo (Cinépolis
`cdmx`, Cinemex el id de estado `8`). El sync escribe `data/logs/sync_status.json` y `scraper.health` lo vigila.

**Etapa 2 (siguiente):** portar `analytics/` a Postgres con tipos nativos, encender el filtro de plaza para lo nacional,
y mover el destino a RDS cuando el cliente confirme la cuenta.

### Pendientes que no dependen del plan 2

- Terminar el paso al servidor (EC2 levantado el 2026-09-10; WARP + Privoxy para Cinépolis): copiar `data/`, dejar un solo
  `sync` apuntando a Postgres y apagar los agentes de launchd (`make launchd-unload`). Comprar el dominio y con él: SES
  (identidad, DKIM, sandbox), `AC_BASE_URL` https, quitar `basic_auth`, aplicar `auth.sql`/`app_role.sql` en RDS y crear el
  primer admin (`make user-create`).
- Cinemex, a mano (`make calibrate-cinemex`, hacia las 7 P.M., por chunks de 60): calibración del semáforo; enciende la
  ocupación estimada de Cinemex en el dashboard.
- Con historia: ocupación por película, franja y complejo desde `occupancy_sample` post-inicio; escala de los colores
  `#FFBE06` / `#FF804A` / `#A2ACBA` (hoy naranja ≈ 83 %, amarillo ≈ 53 % vendido con pocas muestras); comportamiento
  semanal del competidor (cancelaciones, movimientos, hora de publicación); decaimiento por título (≈2026-09-24) y
  tendencia de 4 semanas (≈2026-10-05).
- Tabla de equivalencias de películas entre cadenas (`title_norm` + duración + distribuidor, con revisión manual de
  reestrenos, festivales `tcf-`/`cltcf-` y eventos en vivo).
- Emparejar cines por distancia (zonas de choque) y alcaldía + población INEGI para el panel geográfico.
- Integración con el cliente: aforo oficial, taquilla por función, preventa y su tablero de dulcería.
- **Modelo de tipificación de zonas y consumo por complejo** (esquema de David, 2026-09-08, fuera del repo): arquetipo
  de zona por complejo (isócronas a pie 15 min / auto 20 min, AGEB del Censo 2020, CONAPO, DENUE, afluencia Metro;
  k-means con scikit-learn, geosnap para una v2 por AGEB) y después un modelo de ocupación (LightGBM) cuyo target es el
  plano **post-inicio**. Código en un paquete `geo/` con `requirements-geo.txt` propio, corre en la Mac, resultados en
  `data/geo.db`; `analytics/` sigue sin dependencias. Verificado: INEGIpy da geometrías y DENUE pero no la tabla censal
  por AGEB (va por CSV), y su Ruteo es punto a punto en auto, sin isócronas (usar OpenRouteService). Modelo supervisado
  no antes de finales de octubre de 2026 y solo Cinépolis mientras Cinemex dependa del semáforo.

## Acceso por usuario y explorador de datos (2026-09-10)

Con la infraestructura ya en AWS (falta solo el dominio), el dashboard deja el `basic_auth` compartido de Caddy y pasa a
cuentas por persona. Decisiones de David (2026-09-10): seguir en **Streamlit, misma app** (FastAPI + Next.js sigue
pospuesto), **dos roles** (`admin`: gestiona cuentas y ve todo; `viewer`: gente de Cinemex, ve cartelera, dulcería y
datos), correo por **Amazon SES**, y un **explorador de tablas curadas** con filtros, orden, búsqueda y CSV, sin consola
SQL: es parte del valor que se entrega al cliente, sin regalarle la base completa.

- **Paquetes.** `auth/` (venv, psycopg, boto3): cuentas, sesiones, enlaces de invitación y restablecimiento, correo y
  CLI (`make user-create|user-list|user-reset|user-deactivate|user-activate|auth-prune`); `archive/` (venv, psycopg):
  consultas de solo lectura sobre el archivo en Postgres, mismo estilo que `analytics/` (`fn(conn, ...) -> list[dict]`),
  donde crecerá la etapa 2. `ui/session.py` es el único módulo que conoce la cookie. Las reglas de arquitectura quedan
  enmendadas en `AGENTS.md`: el dashboard sigue sin escribir datos; `auth/` escribe solo el esquema `app` con el rol
  `absolut_app` (`deploy/postgres/auth.sql`, `app_role.sql`; diseño en `docs/postgres-esquema.md`).
- **Sesión.** Streamlit 1.63 solo lee cookies (`st.context.cookies`, en el handshake del WebSocket) y no tiene API para
  escribirlas, así que `ui/session.py` la escribe con JavaScript desde `st.iframe` (mismo origen) y recarga la página;
  `st.rerun()` no basta. Cookie `ac_session` de 30 días deslizantes, `SameSite=Lax`, `Secure` si `AC_BASE_URL` es https,
  sin `HttpOnly` (imposible desde Streamlit; mitigación: token aleatorio, solo su sha256 en la base, revocación al cerrar
  sesión, cambiar contraseña o desactivar; el memo por pestaña se revalida cada 60 s). Se descartó
  `streamlit-cookies-controller` (sin mantenimiento desde 2024) y Cognito/`st.login` (hosted UI, sin las páginas propias).
- **Reglas** (`auth/security.py`, probadas en `tests/test_security.py`): contraseña de 12+ caracteres, `hashlib.scrypt`
  con sal; enlace de invitación 72 h y de restablecimiento 60 min, un solo uso, se invalidan los anteriores; 10 fallos
  seguidos bloquean 15 min; "olvidé mi contraseña" responde igual exista o no la cuenta (verifica contra un hash falso para
  no delatar por tiempo) y emite a lo más 3 enlaces por hora. Nadie se desactiva ni se cambia el rol a sí mismo, ni deja
  el sistema sin admin activo (`SelfChange`, `LastAdmin`). Todo queda en `app.audit`.
- **Navegación** (`app.py`): la lista de páginas depende de la sesión. Sin cookie válida: `login` (raíz), `olvide`,
  `restablecer` (`?token=`), con navegación oculta. Con sesión: Cartelera, Dulcería, Datos y, para admin, Usuarios; la
  página `restablecer` queda oculta pero accesible para que el enlace del correo abra aun con sesión. Una URL que no
  corresponde al rol cae en la página por defecto; `usuarios` además exige admin.
- **Correo.** `AC_MAIL_BACKEND=console` (default) escribe el correo en `data/logs/mail.log`; `ses` envía con boto3 y el
  rol de la instancia (IAM `ses:SendEmail`, identidad del dominio con DKIM; la cuenta nace en sandbox, ver
  `docs/aws-setup.md`). Si el correo falla, la cuenta y el enlace ya existen (`MailFailed` trae el enlace para entregarlo
  por otro canal). Plantillas en `analytics/labels.py` (`MAIL_INVITE`, `MAIL_RESET`).
- **Explorador** (`archive/datasets.py`, `views/datos.py`): seis conjuntos, `cinemas` (complejo con salas y butacas de la
  última medición), `auditoriums`, `week_showtimes` (estado vigente `valid_to IS NULL`, rango de fechas obligatorio para
  podar particiones, por defecto la semana de cine), `ticket_prices`, `concession_prices` y `delivery_prices` (las dos
  últimas con "solo la última lectura" por `DISTINCT ON`). Tope 5,000 renglones con aviso; precios en pesos; conexión con
  `default_transaction_read_only` y `statement_timeout` de 15 s. Medido en local (2026-09-10): todas responden en
  < 200 ms con 66 k funciones.
- **Variables** (`scraper/config.py`, `.env.example`): `AC_AUTH_PG_DSN` (rol `absolut_app`; sin ella usa `AC_PG_DSN`,
  solo aceptable en desarrollo), `AC_MAIL_BACKEND`, `AC_MAIL_FROM`, `AC_BASE_URL`, `AWS_REGION`. Dependencias nuevas del
  dashboard: `psycopg` (ya estaba por el sync) y `boto3`; `streamlit>=1.60`.
- **Verificado (2026-09-10, Postgres local en Docker):** CLI y todos los flujos de `auth/` (invitación, canje, login,
  bloqueo al décimo fallo, restablecimiento con tope, revocación al cambiar contraseña, cierre de sesión, reglas de admin,
  auditoría completa); las páginas recorridas con `streamlit.testing.v1.AppTest` (login, olvide, restablecer con enlace
  bueno y malo, usuarios con cada acción, datos con los seis conjuntos y filtros, viewer sin acceso a usuarios). **Lo que
  falta probar en navegador:** el ciclo de la cookie (entrar, refrescar, cerrar sesión), que `AppTest` no simula.
- **Pendiente con el dominio:** identidad SES + DKIM, `AC_BASE_URL=https://…`, quitar `basic_auth` de Caddy, salir del
  sandbox de SES. Mientras, `console`/`NOMAIL=1` y el enlace se entrega a mano.

## Consideraciones

- La key es pública pero puede rotar con cada despliegue del sitio. Si la API
  devuelve 401, volver a extraerla de los chunks de `/_next/static/chunks/`
  buscando `API_KEY:"`.
- **`api-g.cinepolis.com` está detrás de Cloudflare y su WAF bloquea la IP de salida de AWS** (verificado
  2026-09-10 desde EC2 en us-east-1: `403 Attention Required! | Cloudflare`, error 1020, con la misma clave y
  cabeceras que funcionan desde la Mac; `Origin`/`Referer` no cambian nada; `cinepolis.com` sí responde 200).
  Cinemex no está detrás de Cloudflare y funciona desde EC2. La Mac pasa porque sale por Cloudflare WARP con IP
  mexicana (`cf-ray …-QRO`); el único 403 registrado en la Mac (2026-09-08 18:46 CDMX) coincide con un corte de red.
  El scraper lo reporta como `http.Blocked`, no como clave rotada. **La regla es por ASN de centro de datos, no por
  país**: la misma llamada desde EC2 saliendo por Cloudflare WARP (IP de Cloudflare en EE. UU.) respondió 200 el
  2026-09-10. Solución en el servidor: cliente WARP gratuito en modo proxy (SOCKS5 local) + Privoxy como puente HTTP,
  y `AC_EGRESS_PROXY` en `scraper/config.py` que `http.py` aplica solo a los hosts de `AC_EGRESS_PROXY_HOSTS`
  (`api-g.cinepolis.com`); Cinemex, Rappi y DiDi salen directo. Operación en `deploy/README.md`.
- Los endpoints de billboards no permiten introspección; si un campo falla,
  quitarlo de la query en vez de adivinar alternativas.
- Mantener un ritmo razonable de peticiones. Toda la lista de cines se obtuvo
  con 155 llamadas secuenciales sin ningún error. Un snapshot completo de CDMX de ambas cadenas
  son ~260 llamadas y 2–8 min; cada 15 min no ha provocado bloqueos ni 429 hasta ahora. Los planos
  de Cinépolis sí devuelven errores transitorios si se encadenan sin pausa (ver muestreo).
- launchd en la Mac no es fiable: la noche del 7 al 8 de septiembre durmió ~8 h y al despertar dos
  capturas fallaron sin red (DNS). El dashboard avisa cuando la última captura de una cadena falló o
  el dato tiene más de 45 min.
- Cinemex: si responde `400` de nginx en todo, cambió el `X-API-Consumer-Key`; si responde 404 en
  todo, cambió la versión de ruta (`rest/v2.37.2/`). Ambos se releen del `main.*.chunk.js`. La forma
  del payload también puede cambiar sin aviso y sin cambiar la versión (ver "Cambio de payload
  2026-09-08"): si de pronto una columna de `current_showtime` queda en NULL para toda una cadena
  o aparecen miles de `moved`/`changed` en un solo snapshot, comparar las claves de una sesión del
  crudo nuevo contra el anterior antes de creer el diff.
- `availability` de Cinépolis viene vacío en la mayoría de funciones (12,226 de 12,593 el
  2026-09-07; ver "Asientos y precios" para la calibración con planos reales) y en algunas trae un color: `#FFBE06` amarillo (257), `#FF804A` naranja (105),
  `#A2ACBA` gris (5). **No es la clasificación** (el sitio pinta A verde, B15 amarillo, C rojo,
  pero eso viaja en `rating`): el color va por función, una misma película lo tiene distinto entre
  funciones y el amarillo aparece en A, B, B15 y C. Se concentra en reestrenos y eventos en preventa
  (Avengers, Oasis, Linkin Park, Triplemanía) y el gris solo en eventos en vivo, así que la lectura
  es ocupación: vacío = sin ventas relevantes, amarillo = llenándose, naranja = casi llena, gris =
  agotada. **Confirmado parcialmente con planos reales** el 2026-09-08: dos funciones amarillas
  tenían 32 % y 34 % vendido y una sin color 0 %; la escala exacta sale de `occupancy_sample`. En
  Cinemex es `high`/`mid`/`low`, a calibrar con la pasada `--per-level`.
