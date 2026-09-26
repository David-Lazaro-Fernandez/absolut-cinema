# Plan · Fase 2: la Cineteca Nacional en el dashboard

Escrito el 2026-09-26 para que otro agente lo ejecute en una sesión nueva. Lee primero `AGENTS.md` (convenciones,
obligatorio), luego este plan completo antes de tocar código. Las decisiones marcadas **[DECIDIR]** son del usuario:
pregúntalas al empezar si no están resueltas en el historial del proyecto.

## 1. Contexto

El producto compara **Cinemex** (cliente, `US`) contra **Cinépolis** (competidor, `THEM`). El milestone actual suma
**cines independientes de CDMX**, empezando por la **Cineteca Nacional** (sedes `001` Chapultepec, `002` de las Artes,
`003` México/Xoco).

**Fase 1 (hecha, 2026-09-26): captura.** La Cineteca se captura como `chain="cineteca"` en `data/snapshots.db`, en las
mismas tablas que las otras cadenas. Qué quedó y dónde:

| Pieza | Dónde | Nota |
| --- | --- | --- |
| Cartelera (3/día, trabajo `snapshot`) | `scraper/cineteca.py`, `normalize.cineteca_rows/_cinemas` | JSON público; `show_id = "{sede}:{session_id}"`; `screen` NULL en la cartelera |
| Ocupación post-inicio (cada hora, trabajo `seats`) | `sample.cineteca_layout`, `sample --post-start --chain cineteca` | plano de Vista con token; la sala sale de `Areas[].Description` y se guarda en `occupancy_sample.screen` y `auditorium` |
| Plaza | `scraper/plazas.py`: `PLAZAS["cdmx"]["cineteca"]` | solo para acotar el muestreo; `analytics/plaza.py:_pairs` sigue en dos cadenas a propósito |
| Salud | `scraper/health.py: CHAINS` incluye `cineteca` | |
| Docs | `project.md` › "Cineteca Nacional", `AGENTS.md` (regla "La comparación es de dos cadenas…") | |

Lo que la fase 1 **no** trae: precio (pendiente, ver §7), sala en la cartelera, género, duración ni distribuidora.

**Fase 2 (este plan): presentación.** Una página propia para la oferta independiente, sin tocar el head-to-head
Cinemex↔Cinépolis. Decisión ya tomada con el usuario: la Cineteca **no entra a los shares** de la cartelera (cine de
autor, un solo precio, pocas funciones: mezclarla engañaría; principio 3 de `AGENTS.md`).

## 2. Prerrequisitos (verifícalos antes de empezar)

- **P0 · Estado de git.** La fase 1 quedó **sin commit** (staged) en la rama `cineteca-tercera-cadena`. Confirma con
  `git status`. No hagas push de la fase 1 sin el paso 0 de este plan: `main` → CI → `stable` → servidor cada 15 min, y
  sin el paso 0 la vista nacional mezcla la Cineteca y el explorador de Datos se cae (ver §4).
- **P1 · Semántica del plano de la Cineteca (bloquea los paneles de ocupación).** Supuesto actual en `sample.py`:
  `OriginalStatus != 0` = butaca no vendible, `Status != 0` en una vendible = ocupada. Una sola lectura (función con poca
  venta) salió todo en `Status: 0`. Hay que confirmarlo con una función **muy llena**: el usuario corre
  `/usr/bin/python3 -m scraper.sample --post-start --chain cineteca --limit 5` y compara `sold_pct` contra lo que muestra
  la web. **El agente no puede hacer esa llamada** (el clasificador bloquea usar el token de la app); pídesela al
  usuario. Si la suposición falla, se corrige la regla en `cineteca_layout` y se recalcula desde el histograma que ya
  está en `auditorium.areas_json` (no hay que volver a pedir). Registra el resultado con fecha en `project.md`.
- **P2 · Datos.** La base local no tenía filas de la Cineteca al escribir esto. Hace falta al menos una captura
  (`/usr/bin/python3 -m scraper.run --chain cineteca`) y varios días de `seats` en el servidor para los paneles de
  ocupación. Mientras no haya historia suficiente, esos paneles van como **pendientes** (regla de §6 de `AGENTS.md`).

## 3. Decisiones abiertas [DECIDIR]

Cada una trae la recomendación; confírmala con el usuario.

1. **Dónde vive: página propia.** Recomendado: página `views/independientes.py` ("Independientes") entre Dulcería y
   Datos. `AGENTS.md` pone en la cartelera lo que depende del periodo; esta página sí depende de él, pero meterla en la
   cartelera arriesga mezclarla con los shares. Si se aprueba, documenta la excepción en `AGENTS.md` §6.
2. **Color de la serie Cineteca.** El rojo es Cinemex y la tinta Cinépolis; `OK`/`WARN` son solo de Operaciones.
   Recomendado: gris medio `#8C8E95` (ya está en la paleta divergente) como `INDEP` en `analytics/labels.py`. Documéntalo
   en `DESIGN.md` › Tokens **antes** de usarlo (`AGENTS.md` §4).
3. **Hallazgo de Capa 1.** Recomendado: *"Títulos que llenan la Cineteca y nosotros no exhibimos en CDMX"*. Seguiría el
   patrón de dulcería: entra al ranking global de `findings()` con su `topic` y la página lo filtra. Umbrales sugeridos
   (ajustar con 1–2 semanas de datos): `INDEP_MIN_SOLD_PCT` (ocupación media post-inicio) e `INDEP_MIN_SAMPLES`
   (funciones medidas). Si no hay datos que crucen el umbral, la capa lo dice y no inventa.
4. **Zona.** La Cineteca solo tiene sedes en CDMX. Recomendado: con zona `cdmx` o nacional la página muestra todo; con
   `gdl`/`mty` muestra un aviso ("La Cineteca solo tiene sedes en CDMX") y se detiene. La comparación contra Cinemex usa
   siempre `plaza="cdmx"`.

## 4. Paso 0 · Contener la tercera cadena (bloqueante, va antes o junto con el push de la fase 1)

**Problema verificado el 2026-09-26** (base en memoria con los fixtures de las tres cadenas):

- `_window(plaza=None)` (`analytics/queries.py:55`) no filtra por cadena. Con zona **nacional**, `kpis`, `mix` y
  `concentration` ya devuelven filas `cineteca`, y `movies_by_chain`, `heatmap_day_slot`, `coverage` y `findings` la
  cuentan en sus totales. Con `plaza="cdmx"` no pasa, porque `_pairs` solo admite dos cadenas.
- `plaza_cinema_where(None)` devuelve `""`, así que las tablas de muestreo (`auditorium`, `occupancy_sample`,
  `price_sample`) también la mezclan: `capacity_summary` tendría una fila `cineteca`.
- `views/datos.py:37` hace `CHAIN_LABEL[r.chain]` y `CHAIN_LABEL` no tiene `cineteca`: **KeyError** en cuanto haya un cine
  de la Cineteca en la base. Operaciones (`views/operaciones.py:61,87,125`) solo pinta las dos cadenas de
  `ui/common.CHAINS`, así que la salud de la Cineteca no se ve.

**Arreglo:**

1. En `analytics/labels.py`, junto a `US`/`THEM`: `COMPARED = (US, THEM)`, `CHAIN_LABEL["cineteca"] = "Cineteca
   Nacional"` y `CHAIN_COLOR["cineteca"] = INDEP` (decisión 2).
2. Añade un parámetro con nombre `chains=COMPARED` a `_window`, `plaza_where`, `plaza_cinema_where` y `_pairs`:
   - con `plaza=None` → `AND {alias}chain IN (…)` en vez de `""`;
   - con plaza → `_pairs(plaza, chains)` recorre solo esas cadenas (la Cineteca entra si se pide, porque ya está en
     `PLAZAS["cdmx"]`).
   Así el default protege el head-to-head y las funciones de la Cineteca piden `chains=("cineteca",)` o
   `("cineteca", US)`.
3. Audita cada llamada: 12 a `_window` (queries 6, seats 4, headlines 1, summary 1), 6 a `plaza_where` (queries 3,
   history, presale, plaza) y 13 a `plaza_cinema_where` (seats 7, queries 3, presale 2, concessions 1). Las funciones
   con parámetro `chain=` explícito (`occupancy_summary`, `occupancy_recent`, `occupancy_by_title`,
   `capacity_by_cinema`, `offered_by_title`, `semaphore_calibration`, `estimated_occupancy`, `presale_*`,
   `recent_events`) deben pasar `chains=(chain,)`; si no, `chain="cineteca"` más el default `COMPARED` devuelve vacío.
   `plazas()` y `plaza_coverage()` (selector y Operaciones) pueden seguir con el default.
4. Explorador de Datos (sí debe ver las tres): opciones de cadena `[None, *CHAIN_LABEL]` en `views/datos.py:32`, y
   `DATA_TEXT["both"]` pasa de "Ambas" a "Todas" (o usa `DATA_TEXT["all"]`). Revisa `analytics/datasets.py`: sus
   funciones reciben `chain` opcional y no filtran por plaza, así que ya incluyen la Cineteca; está bien ahí.
5. Operaciones: la tabla de señales y el gráfico de corridas recorren las cadenas del reporte
   (`[c for c in CHAIN_LABEL if report["chains"].get(c)]`), con el dominio de color de las tres.
6. **Prueba (pura, entra a CI):** `tests/test_chain_scope.py`. Base en memoria con `store.SCHEMA`, cargada con
   `scripts/capture_fixtures.replay(chain)` + `run.commit` para las tres cadenas (así se hizo la verificación del
   2026-09-26; copia ese patrón de `tests/test_capture_replay.py`). Afirma que con `plaza=None` ninguna función
   head-to-head (`kpis`, `mix`, `concentration`, `movies_by_chain`, `heatmap_day_slot`, `showtimes_by_slot`,
   `coverage`, `capacity_summary`, `findings`, `conclusions`) devuelve ni cuenta filas `cineteca`, y que
   `occupancy_recent(chain="cineteca")` sí las devuelve (inserta un par de `occupancy_sample` sintéticas).

Este paso se puede mergear solo. Hazlo primero.

## 5. Paso 1 · Títulos: que la Cineteca empate con Cinemex

- `scraper/titles.py` › `_DECORATIONS`: regla para el sufijo de idioma de la Cineteca, `re.compile(r" (dob|dub|sub)$")`,
  con su caso (`"Cars 20 aniversario DOB"` → `cars`). Va **antes** de la regla de aniversario en la lista, porque se
  aplican en orden. Prueba en `tests/test_titles.py`. Revisa que no cambie ninguna llave de Cinemex ni de Cinépolis:
  compara `title_key` de todos los `title_norm` de la base antes y después.
- `scripts/title_pairs.py:32` solo propone pares Cinemex↔Cinépolis. Añade una opción (p. ej. `--vs cineteca`) que llame
  `titles.candidates(load_titles(conn, "cinemex"), load_titles(conn, "cineteca"))`. Los pares dudosos los decide una
  persona (`scraper/title_pairs.csv`), nunca el parecido automático (`AGENTS.md` §1). Mucho cine de autor no tendrá
  pareja: es el dato, no un error.

## 6. Paso 2 · Funciones en `analytics/` (stdlib, sin pandas)

Módulo nuevo `analytics/independents.py`. Firma como las existentes (`AGENTS.md` §3): `fn(conn, d0=None, d1=None,
from_now=True, hours=None, …)`, lista de dicts en `snake_case`, `ORDER BY` explícito, exportada en
`analytics/__init__.py` y en `__all__`. Usa `_window(…, chains=(chain,))` del paso 0 y agrupa títulos con
`title_key(title_norm)`. **Imprime cada función una vez con datos reales antes de conectarla** (`AGENTS.md` §8).

| Función | Devuelve | Nota |
| --- | --- | --- |
| `independent_summary(conn, d0, d1, from_now=True, hours=None, chain="cineteca")` | por sede: `cinema_id`, `cinema_name`, `shows`, `titles`, `days`, `share_shows` | % de la programación de la propia cadena |
| `independent_titles(…, chain="cineteca", limit=40)` | por `title_key`: `title_norm`, `title`, `shows`, `cinemas`, `share_shows`, `subtitled`, `spanish`, `other`, `first_date`, `last_date` | `language="other"` = sin marca de idioma (lengua original) |
| `independent_slots(…, chain="cineteca", vs=US, plaza="cdmx")` | por franja (`labels.SLOTS`) y cadena: `slot`, `chain`, `shows`, `share` | shares de cada cadena, comparables; la Cineteca contra Cinemex CDMX |
| `independent_overlap(…, chain="cineteca", vs=US, plaza="cdmx")` | por `title_key`: `shows_indep`, `shows_vs`, `cinemas_vs`, `status` ∈ {`shared`, `indep_only`} | más un resumen: % de funciones de la Cineteca con título que también exhibimos |
| `occupancy_by_cinema(conn, days=7, chain="cineteca", phase="post", plaza=None)` (en `seats.py`, genérica) | por sede y franja: `cinema_id`, `cinema_name`, `slot`, `samples`, `sold_pct`, `seats` | usa `occupancy_sample.screen`, no la cartelera |

Reutiliza sin copiar: `occupancy_by_title(chain="cineteca", min_samples=…)` (baja `min_samples`: son 3 sedes y ~120
funciones al día) y `occupancy_recent(chain="cineteca")`. **No uses** `occupancy_summary` (agrupa por el semáforo de
Cinemex; la Cineteca no tiene `availability`) ni `offered_seats`/`offered_by_title` (unen por `screen` de la cartelera,
que en la Cineteca es NULL).

## 7. Paso 3 · Hallazgo, textos y color

- `analytics/findings.py`: `_independent_finding(conn, d0, d1, …)` con `topic="independientes"`, umbrales como
  constantes arriba del módulo (decisión 3), texto en primera persona como Cinemex. Solo afirma si cruza el umbral y si
  P1 está confirmado. Añade la conclusión de cada pregunta de la página a `conclusions()`.
- `analytics/labels.py`: un dict `INDEP_TEXT` con título de página, preguntas, notas, textos de "Cómo leerla",
  pendientes y estados de solape (`shared` → "También en Cinemex", `indep_only` → "Solo en la Cineteca"). Ningún texto
  en la vista (`AGENTS.md` §4). Ningún hex fuera de `labels.py`.
- `DESIGN.md`: el token nuevo (decisión 2) y una línea en "Aplicación en este repo" sobre la página.

**Precio:** no hay dato; va como pendiente en Capa 3 con lo que lo desbloquea: el boleto `GENERAL` ($70.00 el
2026-09-26) está en `visSelectTickets.aspx`, que pide el handshake de cookie de ASP.NET (hay que darle un
`http.cookiejar` a `scraper/http.py`), o el endpoint de boletos de Connect API, sin verificar. Sin cifra en pantalla
hasta capturarlo (`AGENTS.md` §2, principio 1).

## 8. Paso 4 · La página `views/independientes.py`

Copia la estructura de `views/dulceria.py` (la página propia más parecida): `from ui.common import *`, guarda de
`config.DB_PATH`, `plaza_selector()` (decisión 4), encabezado `enc`, tres capas con `capa`, `seccion`, `pregunta`,
`leyenda`, `chart`, `leerla`, `apendice`. Todo dato entra por `load(...)`; el texto de la base pasa por `esc()`.
Periodo: semana de cine (`analytics.cinema_week`) con el mismo selector de la barra lateral que `views/cartelera.py`
(líneas 18–45); la Cineteca publica hasta el miércoles, no más allá.

- **Capa 1 · Lo que importa hoy**: `findings()` filtrado por `topic == "independientes"`, o el aviso de que nada cruza el
  umbral.
- **Capa 2 · Evidencia**, cada sección en el orden fijo (pregunta, conclusión, leyenda, gráfico, controles, "Cómo leerla"):
  1. *¿Qué programa la Cineteca esta semana?* `independent_summary` + `independent_titles` (barras por título, color de
     la Cineteca).
  2. *¿Cuánto se llena?* `occupancy_by_cinema` + `occupancy_by_title`. **Pendiente** mientras P1 no esté confirmado o no
     haya muestras suficientes; nada de series de un punto.
  3. *¿Compite con nuestra cartelera?* `independent_overlap`: % de sus funciones con título que también exhibimos en
     CDMX, y la lista de títulos solo suyos con su ocupación (la oportunidad).
  4. *¿A qué horas programa?* `independent_slots`: share por franja, Cinemex primero y en rojo, Cineteca en su color.
- **Capa 3 · Apéndice**: cartelera completa de la semana, aforo por sala (`capacity_by_cinema(chain="cineteca")`) y
  pendientes (precio; sala en la cartelera, que solo llega del plano).

`app.py`: `st.Page("views/independientes.py", title="Independientes", icon=":material/theaters:",
url_path="independientes")` después de Dulcería, para ambos roles.

## 9. Paso 5 · Pruebas y documentación

- `tests/test_independents.py` (pura, CI): base en memoria como en el paso 0 más `occupancy_sample` sintéticas; comprueba
  shares que suman 100 por cadena, el solape con un par de títulos que empatan tras la regla DOB/SUB y el orden
  determinista.
- `tests/test_views.py`: `test_independientes_for_viewer` con `needs_sqlite` (se omite en CI) y que el explorador de
  Datos no se caiga con cines de la Cineteca.
- Docs: `AGENTS.md` §6 (lista de páginas y la excepción de la decisión 1), `project.md` › Dashboard (la página, sus
  preguntas y los umbrales), `DESIGN.md` (color y página), `README.md` si cambia la entrada.

## 10. Verificación

```sh
make check                                                   # lint, imports con el Python del sistema, pytest
/usr/bin/python3 -c "import analytics; print(analytics.independent_summary(analytics.connect()))"   # cada función, una vez
make dashboard                                               # recorre la página con zona CDMX, Nacional y Guadalajara
```

- Con zona **Nacional**, la cartelera muestra las mismas cifras que antes del cambio (compara `kpis`/`mix` contra `main`).
- Datos: filtra "Todas" y "Cineteca Nacional"; ningún error.
- Operaciones: la Cineteca aparece en señales y corridas.
- Página Independientes: sin cifras en ocupación mientras P1 esté pendiente; con `gdl` muestra el aviso.

## 11. Orden y qué se puede entregar por separado

1. **Paso 0** (y la fase 1 con él): se mergea solo y es requisito para hacer push de la fase 1.
2. **Pasos 1–2**: títulos y funciones; entregables sin tocar la UI (se ven en Datos y con `print`).
3. **Pasos 3–5**: hallazgo, textos, página y pruebas.

Los paneles de ocupación y el hallazgo dependen de P1 y de días de datos: la página puede salir antes con ellos como
pendientes y encenderlos después sin rehacer nada.

## 12. Fuera de alcance

Otros cines independientes (seguirán el mismo patrón: captura aditiva, `chains=` explícito, esta misma página); precio
de la Cineteca (§7); sala y ficha (duración, género) desde `detallePelicula.php`; aforo por `--capacity` de la Cineteca
(agrupa por la sala de la cartelera, que es NULL).
