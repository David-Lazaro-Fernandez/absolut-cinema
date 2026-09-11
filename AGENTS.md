# AGENTS.md

Guía para agentes de código (Claude Code, Cursor, Copilot) y para cualquier persona que edite este
repo. Es la fuente de verdad de convenciones. Lo que **no** va aquí:

- `project.md` — cómo funcionan las APIs de ambas cadenas, modelo de datos, estado y decisiones.
- `ARCHITECTURE.md` — qué proceso toca qué dato, qué lo programa, catálogo de servicios.
- `DESIGN.md` — paleta, tipografía, componentes y reglas visuales del dashboard.
- `deploy/README.md` — operación del servidor.
- `make help` — comandos.

Antes de proponer un cambio, lee la sección que le toca. Si el cambio contradice algo de aquí,
dilo explícitamente en vez de hacerlo a medias.

## 1. Panorama

Inteligencia competitiva de cartelera para **Cinemex** (el cliente) frente a **Cinépolis** (el
competidor), plaza piloto CDMX. Tres capas, sin mezclarse:

| Capa | Carpeta | Dependencias | Escribe |
| --- | --- | --- | --- |
| Captura | `scraper/` | **solo stdlib**, `/usr/bin/python3` | `data/snapshots.db`, `data/raw/`, `data/logs/` |
| Negocio | `analytics/` | **solo stdlib** | nada (abre la base en `mode=ro`) |
| Presentación | `app.py` + `ui/` + `views/` | `.venv` (streamlit, pandas, altair) | nada |
| Archivo histórico | `sync/` | `.venv` (psycopg) | PostgreSQL (`AC_PG_DSN`) y `data/logs/sync_status.json` |
| Acceso | `auth/` | `.venv` (psycopg, boto3) | PostgreSQL, **solo el esquema `app`** (cuentas, sesiones, enlaces, auditoría) con el rol `absolut_app` |
| Archivo, lectura | `archive/` | `.venv` (psycopg) | nada (abre Postgres en `default_transaction_read_only`) |

### Reglas de arquitectura (no negociables sin discutirlo)

- **El scraper no tiene dependencias externas.** Corre con el Python del sistema en un servidor
  pelado. Si necesitas algo que no está en la stdlib, la respuesta por defecto es implementarlo en
  `scraper/http.py` o replantear el cambio. Igual para `analytics/`: sin `pandas` ni nada más.
- **`analytics/` no importa Streamlit ni pandas** y no sabe que existe un dashboard. Son funciones
  puras: reciben `conn` y parámetros, devuelven listas de dicts. Están escritas así para envolverlas
  después en un API (FastAPI) sin reescribir nada.
- **La presentación no lleva SQL ni lógica de negocio.** `app.py` es la entrada (configuración, CSS y
  `st.navigation`), `ui/common.py` los helpers compartidos y `views/*.py` una página por módulo. Solo pintan lo que
  devuelve `analytics/`. Si para una vista nueva hace falta un cálculo, va en `analytics/`, no en el dashboard.
- **Un solo escritor** sobre `snapshots.db`. Todo lo que escribe corre en serie desde el mismo timer
  o en minutos distintos (`:07`). No añadas un proceso escritor sin ubicarlo en ese calendario.
- **El dashboard nunca escribe datos.** `analytics.connect()` abre SQLite en `mode=ro` y `archive.connect()` abre
  Postgres en solo lectura, a propósito. Lo único que escribe desde el dashboard es `auth/`, y solo en su esquema `app`
  (cuentas, sesiones, enlaces de acceso, auditoría); las vistas no lo llaman directo, pasan por `ui/session.py` y
  `load_auth`. `ui/session.py` es el único módulo que conoce la cookie de sesión.
- **`sync/` es el único escritor del archivo histórico en PostgreSQL** (esquema `public`) y lo hace por marca de agua y
  `ON CONFLICT DO NOTHING`: el archivo es append-only, nadie borra ahí de forma automática. `archive/` lo lee y `auth/`
  escribe solo `app`; ninguno importa `sync/`, y `scraper/`, `analytics/` y `sync/` jamás importan `auth/` ni `archive/`.
  `auth/` y `archive/` tampoco importan Streamlit. Lee SQLite en `mode=ro` y el crudo; puede importar
  `scraper.config`, `scraper.normalize` y `scraper.diff` (stdlib), pero el scraper jamás importa `sync/`. Las reglas de
  "qué cuenta como cambio" y "cómo se cierra una función" viven en `scraper/diff.py` (`changed_fields`,
  `closing_kind`) y `scraper/normalize.py` (`TRACKED_FIELDS`); scraper, dashboard y sync las comparten y no se duplican.
- **`app.py` vive en la raíz a propósito**: Streamlit solo recarga en caliente los módulos bajo la
  carpeta del script, así `ui/`, `views/`, `analytics/`, `archive/`, `auth/` y `scraper/` también se recargan al
  editarlos. No lo muevas.

## 2. Principios de producto

Estos mandan sobre cualquier preferencia técnica.

1. **Datos reales siempre.** Lo que no existe no se muestra con cifras. Sin placeholders, sin datos
   de ejemplo, sin "aproximadamente". Si un panel depende de historia o de una integración que no
   está, se declara como pendiente en la Capa 3 y se dice qué desbloquea.
2. **Umbral antes de afirmación.** Un hallazgo de Capa 1 solo se redacta si cruza su umbral
   (`analytics/findings.py`). Si ninguna diferencia lo cruza, la capa lo dice y no inventa.
3. **Shares, no absolutos.** Toda medida comparable entre cadenas es % de la programación de cada
   cadena. Cinemex y Cinépolis tienen distinto número de cines y salas; un absoluto engaña.
   Denominador actual: funciones. Cuando haya aforo completo pasará a butacas ofertadas.
4. **Comparación justa del día en curso.** Cinépolis borra cada función al empezar y Cinemex la
   conserva unas horas. Cualquier consulta que incluya hoy usa `from_now=True` (por defecto).
5. **La semana de cine es jueves a miércoles.** Es lo que ambas cadenas publican completo. Usa
   `analytics.cinema_week()`, no `isocalendar()`.
6. **Hablamos como Cinemex, en primera persona.** `US`/`THEM` en `analytics/labels.py`.

## 3. Python

- Versiones: el scraper y `analytics/` deben correr en `/usr/bin/python3` (3.9+); el dashboard usa
  el venv (3.12).
- PEP 8 y el Zen de Python. Código elegante y legible antes que ingenioso.
- **Evita la herencia** (prefiere composición) y **evita las clases** salvo para excepciones. Este
  repo son funciones y módulos; que siga así.
- Nombra funciones y variables de forma que no haga falta un comentario para entenderlas.
- Archivos y carpetas en `snake_case`.
- **Importa módulos, no funciones sueltas**, cuando el módulo aporta contexto:
  `from scraper import config` → `config.DB_PATH`. Para constantes y helpers de un mismo paquete,
  el import directo está bien (`from .labels import SLOTS`).
- **Todo lo privado de un módulo lleva `_`** (`_window`, `_FORMAT_CASE`). Si no lleva `_`, es API
  del módulo y alguien puede depender de ello.
- **Argumentos**: posicionales solo los que enmarcan la función (`conn`, `d0`, `d1`). Todo lo que
  matiza va con nombre y con default que sirva para el 80% de los casos (`from_now=True`,
  `limit=60`, `chain="cinepolis"`).
- Comentarios: mayúscula inicial, gramática y puntuación correctas, en español. Un comentario
  describe **el comportamiento actual o el por qué**, nunca cómo era antes ni el historial.
  Los porqués valiosos son los de las APIs ajenas (por qué hay una pausa, por qué un lote es de 30).
- Docstrings: para quien **usa** la función, no para quien la va a editar. Si le quieres hablar al
  siguiente que edite, usa un comentario. Todo módulo lleva docstring de nivel superior con qué
  hace y qué supuestos tiene.

### Vocabulario estándar

Los mismos nombres en todo el repo. Esto es sagrado; renombrar rompe la lectura cruzada de SQL,
`analytics/` y `app.py`.

| Nombre | Significado |
| --- | --- |
| `chain` | `"cinemex"` \| `"cinepolis"` |
| `conn` | conexión SQLite de solo lectura, siempre primer argumento en `analytics/` |
| `d0`, `d1` | rango de fechas ISO inclusivo, en hora local de la plaza |
| `from_now` | recorta el día en curso para comparar justo |
| `show_id` | función; Cinemex id nacional, Cinépolis `slug-del-cine:sessionId` |
| `cinema_id` | Cinépolis por `slug`, Cinemex por id numérico |
| `screen` | sala; la llave de aforo es `(chain, cinema_id, screen)` |
| `minutes_to_start` | ≥ 0 preventa (T−60), < 0 asistencia (post-inicio) |
| `pp` | puntos porcentuales (diferencias entre shares) |

### Consistencia de la API de `analytics/`

Cada función nueva se parece a las que ya existen: `fn(conn, d0=None, d1=None, from_now=True)`,
devuelve lista de dicts con claves en `snake_case` en inglés, y ordena de forma determinista
(`ORDER BY` explícito siempre; sin `ORDER BY` el mismo dato puede pintar distinto entre recargas).
Exporta en `analytics/__init__.py` y añádela a `__all__`. Antes de inventar una función nueva,
mira si extender una existente con un parámetro con nombre cubre el caso.

## 4. Textos, colores y etiquetas

- **Ningún nombre interno llega al usuario.** `chain`, `kind`, claves de franja y de cubeta se
  traducen en `analytics/labels.py`. Si un texto aparece en pantalla, sale de `labels.py` (etiquetas)
  o de `findings.py` (frases), nunca escrito en `app.py`, `ui/` ni `views/`.
- **Ningún hex se escribe en la presentación (`app.py`, `ui/`, `views/`).** Los colores viven en `analytics/labels.py` (`RED`, `INK`,
  `GRAY`, `LINE`, `CHAIN_COLOR`, `RED_RAMP`, `DIVERGING`…). Para un color nuevo: agrégalo a
  `labels.py` y documéntalo en `DESIGN.md` **antes** de usarlo.
- **Rojo = Cinemex o acción. Cinépolis = tinta (`#191A1E`).** El rojo no se usa para alertas ni para
  valores negativos. Cinemex siempre primero en las escalas; las series no se ciclan.
- Formato para directivos: horas en 12 h, fechas en español, números tabulares. Usa los helpers
  (`date_es`, `range_es`, `time_12`, `n`, `pp`), no `f"{x:.1f}"` a mano.

## 5. Captura (`scraper/`)

- **Respeta el ritmo de las APIs ajenas.** `PAUSE_BETWEEN_CALLS`, `SAMPLE_PAUSE`, `SAMPLE_BACKOFF`,
  `RETRIES` y el tope por corrida de la calibración existen porque las APIs devuelven errores
  transitorios si se les aprieta. No los bajes para "ir más rápido"; si un flujo necesita otro
  ritmo, añade una constante en `config.py` con un comentario que diga qué error evita.
- **Todo lo configurable pasa por `scraper/config.py`** y admite sobreescritura por variable de
  entorno (`AC_DATA_DIR`, `CINEPOLIS_API_KEY`, `CINEMEX_BASE_URL`, `AC_EGRESS_PROXY`…). Nada de URLs, claves, ids de
  área o rutas escritos dentro de un módulo.
- **Excepciones**: usa las de `scraper/http.py` en vez de levantar `ValueError`/`RuntimeError`
  genéricos. `AuthError` (401, o 403 con JSON) significa casi siempre que la clave embebida rotó y hay que
  actualizar `config.py` y `project.md`; `Blocked` (403 con página HTML) que el WAF del borde rechaza la IP de
  salida y la clave está bien; `RateLimited` (429) que hay que bajar el ritmo; `ApiError` el resto. Un error nuevo con causa distinta merece su subclase, no un mensaje suelto.
- **Guarda el crudo.** Cada snapshot deja su `raw/{chain}/{fecha}/*.json.gz`. Es lo que permite
  recalcular sin volver a pedir. No añadas un flujo que descarte la respuesta original.
- **Los cambios de esquema van en `store.py`** con `CREATE TABLE IF NOT EXISTS` y son aditivos: la
  base de producción tiene historia desde el 2026-09-07 y no se recrea. Una columna nueva se agrega,
  no se renombra.
- Un fallo de una cadena no debe tumbar la corrida de la otra; el snapshot se registra con `ok=0` y
  `error`, y `scraper.health` lo reporta.

### Registro (logs)

Los timers y los agentes solo ven la consola y `data/logs/`. Registra lo que un humano o un agente
necesita para diagnosticar: fallos de API, huecos de captura, respuestas degradadas, fallbacks
inesperados. **No sobre-registres**: el ruido esconde los problemas reales. Un caso raro que se
puede resolver sin que importe se maneja en silencio.

`scraper.health` es el que decide si la captura está sana y **sale con 1 si hay problemas** para que
el timer lo note. Si añades un flujo de captura, añade su cobertura ahí.

## 6. Dashboard (`app.py`, `ui/`, `views/`)

- Páginas con `st.navigation` (barra superior; en celular el CSS la fija abajo): `views/cartelera.py` (tres
  capas con los filtros de periodo y franja en la barra lateral), `views/dulceria.py`, `views/datos.py` (explorador del
  archivo en Postgres) y, solo para el rol admin, `views/usuarios.py` y `views/operaciones.py`. Un módulo que responde una
  pregunta propia del cliente y no depende del periodo va en su página; lo demás, en la cartelera. Las páginas
  hacen `from ui.common import *` a propósito: comparten un espacio de nombres de presentación.
- **`views/operaciones.py` es la excepción documentada** a "ningún nombre interno llega al usuario": su público es quien
  opera la plataforma, así que muestra nombres de tablas, logs y módulos tal cual, y usa los colores de estado `OK` y
  `WARN` de `labels.py` (los únicos que no son rojo ni tinta). Su lógica vive en `scraper/health.py` (SQLite y `data/`,
  stdlib) y `archive/status.py` (Postgres, solo lectura); entra por `load_health`, `load_ops` y `load_pg_raw`. Nada de
  esa página escribe ni ejecuta acciones: es un tablero de lectura, no una consola.
- **La lista de páginas depende de la sesión** (`app.py`): sin cookie válida solo existen `views/login.py`,
  `views/olvide.py` y `views/restablecer.py` (navegación oculta). Streamlit resuelve la URL contra esa lista, así que una
  ruta que no corresponde al rol cae en la página por defecto; `views/usuarios.py` además abre con `require_admin`.
  Las páginas de acceso no tocan `snapshots.db` y solo hablan con `ui/session.py`.
- Estructura fija de tres capas (hallazgos → evidencia → apéndice), descrita en `DESIGN.md` y
  `project.md`. Una sección de evidencia va siempre en el mismo orden: pregunta, conclusión,
  leyenda, gráfico, controles, "Cómo leerla". Reutiliza los helpers (`capa`, `seccion`, `pregunta`,
  `leerla`, `apendice`, `leyenda`, `table`, `chart`), no repliques el HTML.
- **Todo dato entra por `load()` / `load_raw()`** (SQLite, `ttl=TTL`), **`load_pg()`** (archivo en Postgres, `ttl=TTL_PG`)
  o **`load_auth()`** (cuentas, sin caché); los tres cierran la conexión. No abras conexiones sueltas ni llames a
  `analytics`, `archive` o `auth` directamente en el cuerpo de la página.
- **El HTML crudo se escapa.** Cualquier texto que venga de la base y se pinte con
  `unsafe_allow_html=True` pasa por `esc()`.
- **Paneles dependientes de historia**: si un panel necesita más días de los que hay desde
  `FIRST_SNAPSHOT`, se muestra como pendiente con lo que desbloquea, no con una serie de un punto.
- El cálculo va en `analytics/`. Si te encuentras escribiendo un `groupby` de pandas con lógica de
  negocio en una vista, es señal de que falta una función en `analytics/`.

## 7. Shell y despliegue

- **Toda variable entre comillas** (`"$BACKUP_BUCKET"`, `"$(dirname "$0")"`). Una ruta o un nombre
  sin comillar se rompe con un espacio.
- `deploy/*.sh` son bash con `set -euo pipefail`: instalar o respaldar a medias es peor que fallar.
- `scraper/*.sh` (los que lanza launchd) **no** llevan `set -e` a propósito: cada paso escribe su
  log y una captura que falla no debe cancelar las siguientes del mismo tick. Mantén ese
  comportamiento si añades un paso.
- Nada de secretos en el repo. Van en `deploy/absolut-cinema.env` (con `.example` versionado).
- Cada unidad de systemd/launchd nueva ejecuta **un target de `make`**, no un comando inline. Así
  cualquier cosa que corre en automático se puede reproducir a mano igual.
- Los servicios de escritura diarios corren en `:07`, las capturas de cartelera en `:30` y el pase de butacas en `:50`, para no chocar entre sí.

## 8. Verificar un cambio

`make check` es la compuerta: `ruff` (reglas en `pyproject.toml`), la comprobación de que `scraper/` y `analytics/`
compilan e importan con el Python del sistema, y `pytest`. Lo corre el hook `pre-push` (`.githooks/`, se activa una
vez por clon con `make hooks`) y el workflow de GitHub que mueve la rama `stable`; si falla en local no hay push, y si
falla en CI no hay despliegue. `ruff` no bloquea por largo de línea ni por los `;` que agrupan pasos cortos (el repo los
usa a propósito); sí por imports sin usar, nombres sin definir, orden de imports y llaves repetidas en un dict.

La verificación principal es correr el flujo de verdad contra la base. Hay además pruebas unitarias en
`tests/` (pytest, `requirements-dev.txt`, solo en el venv): lógica pura que no toca red (diff de snapshots, sync,
parsers, seguridad de cuentas, filtros del explorador) y un recorrido por pantalla con `AppTest`
(`tests/test_views.py`: acceso, cartelera, dulcería, datos y usuarios, por rol), que se omite donde no hay
`data/snapshots.db` o el Postgres de desarrollo. Corre `.venv/bin/python -m pytest -q tests/` si tocas `scraper/diff.py`,
una vista o añades lógica pura; añade una prueba cuando el caso quepa en memoria y, si es una pantalla, en `test_views.py`. Antes de dar por bueno un cambio:

```sh
make help                                  # los targets son lo que corren los timers
/usr/bin/python3 -m scraper.run            # snapshot completo de ambas cadenas (~5 min)
/usr/bin/python3 -m scraper.health         # sale 1 si hay huecos o fallos
make dashboard                             # Streamlit local
sqlite3 data/snapshots.db "SELECT * FROM snapshot ORDER BY id DESC LIMIT 4;"
```

- **Ejecuta el módulo que tocaste**, no solo el que te queda a mano. Un cambio en `normalize.py` o
  `store.py` se verifica con un `scraper.run` real; uno en `analytics/` levantando el dashboard y
  mirando el panel; uno en `sample.py` con el flag correspondiente y `--limit` bajo.
- **Verifica con el scraper del sistema, no con el venv**, para que un import accidental de una
  dependencia externa falle aquí y no en el servidor:
  `/usr/bin/python3 -c "import analytics, scraper.run, scraper.sample"`.
- Los flujos que abren órdenes de checkout (`capacity-cinemex`, `calibrate-cinemex`) se lanzan **a
  mano y con tope**. No los pongas en un automatismo ni subas su límite sin pedirlo.
- Si añades una función a `analytics/` o `archive/`, imprímela una vez con datos reales antes de conectarla al
  dashboard; es más rápido que depurar dentro de Streamlit.
- Acceso: `make pg-up pg-schema auth-schema` deja el esquema `app` y el rol `absolut_app` en el Postgres local;
  `make user-create EMAIL=… NAME=… ROLE=admin` imprime el enlace de invitación (con `AC_MAIL_BACKEND=console` también
  queda en `data/logs/mail.log`). Las páginas se pueden recorrer sin navegador con `streamlit.testing.v1.AppTest`
  parcheando `ui.session._raw_cookie`; lo que solo un navegador prueba es la cookie (entrar, refrescar, salir).

## 9. Al terminar

- Sigue los patrones de los archivos vecinos antes que cualquier preferencia general.
- Actualiza la documentación que el cambio invalide, en el archivo que le toca: `project.md`
  (APIs, modelo de datos, decisiones), `ARCHITECTURE.md` (flujo, servicios, cadencias), `DESIGN.md`
  (color, tipografía, componentes), `deploy/README.md` (operación), `README.md` (entrada).
- Un servicio o target nuevo entra en el catálogo de `ARCHITECTURE.md` y en `make help`.
- Documenta con fecha lo que se verificó contra la API ajena (`verificado 2026-09-08`); estas APIs
  no tienen contrato y lo que hoy responde puede cambiar.
- `data/` está fuera de git. No versiones la base, el crudo ni los logs.
- La rama principal es `main`. No hagas commit ni push salvo que se te pida. La rama `stable` la mueve GitHub Actions
  (`.github/workflows/tests.yml`) cuando las pruebas pasan en `main`, y es lo que el servidor despliega cada mañana
  (`make deploy`, 07:07): no la muevas a mano. Si un commit rompe las pruebas, `stable` se queda atrás hasta que se
  arregle; por eso una prueba que falla en CI bloquea el despliegue de todo lo posterior.
