# design.md — sitio de marketing de Matiné

Guía para cualquier persona o agente que edite `marketing/`. Es al sitio público lo que
`../DESIGN.md` es al dashboard: la referencia que evita que cada cambio reinvente la marca. Si vas
a tocar `app/`, `components/` o `app/globals.css`, lee esto primero.

## 1. Qué es este sitio y para quién

`marketing/` es la landing page pública de **Matiné**, el nombre externo del producto: inteligencia
competitiva de cartelera para exhibidores de cine. Internamente el repo y el dashboard siguen
llamándose Absolut Cinema (`AUTH_TEXT["app_name"]` en `analytics/labels.py`, correos de invitación,
título de la app) — ese es el nombre del lado privado, que solo ve Cinemex, y no cambia aquí. Matiné
es el nombre con el que el producto se presenta a cualquier otra cadena. El lector de esta página es
alguien en dirección comercial o revenue management de **una cadena de cine que no es Cinemex** — hoy
sin acceso al producto — decidiendo si vale la pena pedir una demo. Su trabajo en la página es uno
solo: entender qué hace el producto en los primeros diez segundos y decidir si escribe.

No es un blog y no necesita servidor: es contenido estático (`next.config.mjs` usa `output: 'export'`). Tiene tres
rutas: la portada, `/a-donde-ir/`, la demo pública del recomendador (§7), que le enseña a cualquiera —no solo a una
cadena— lo que Matiné sabe de la cartelera con datos reales, y `/request-demo/`, el formulario para pedir una demo.
Todo "Solicitar acceso" lleva ahí (`DEMO_URL` en `lib/site.ts`).

## 2. Identidad heredada, no inventada

Este sitio **reutiliza la identidad visual del dashboard**, documentada en `../DESIGN.md` y
`../analytics/labels.py`. No se inventa una paleta ni una tipografía nueva para "marketing": el
producto debe verse igual antes y después de iniciar sesión.

- **Colores.** Los mismos tokens de `analytics/labels.py`: rojo `#E31837` (Cinemex, y aquí también
  "acción": el único botón sólido de la página es la invitación a escribir), tinta `#191A1E`
  (texto fuerte y la sección oscura), gris `#5C6068` (texto secundario), línea `#E4E5E9` (bordes y
  hairlines), papel `#FFFFFF`, fondo `#F6F6F4`, rojo suave `#FDEDF0` (hover y el subrayado del hero).
  Viven en `app/globals.css` como variables (`--red`, `--red-dark`, `--red-soft`, `--ink`, `--gray`,
  `--line`, `--paper`, `--bg`) más transparencias derivadas de la tinta y el papel (`--ink-05` …
  `--ink-30`, `--paper-10` … `--paper-85`) para rejillas y la sección oscura. **No se escribe un hex
  en el JSX**; hasta el canvas de la esfera lee `--ink` con `getComputedStyle`.
- **Tipografía.** Una sola familia, **Archivo** (variable, Google Fonts), con eje de anchura para
  títulos — la misma URL que carga `ui/common.py`:
  `family=Archivo:ital,wdth,wght@0,62..125,400..900;1,62..125,400..900`. Los títulos usan
  `font-stretch` condensado (75–82 %), igual que `.enc h1`, `.capa-tag h2` y `.marca` del dashboard.
  Donde una página de referencia usaría una monoespaciada (rótulos, numeración `01`), aquí va Archivo
  en mayúsculas con tracking (`.eyebrow`, `.feat__num`, `.hgrid__idx`) y `tabular-nums`.
- **Wordmark.** "Matin**é**": una sola palabra, así que la regla del dashboard ("segunda palabra en
  rojo") no aplica tal cual — aquí el acento, la única tilde del nombre, va en rojo como el detalle
  que se colorea (`.marca span` es la misma clase que en `ui/common.py`, solo cambia qué envuelve).
  No se usa otro logotipo ni isotipo: no existe uno todavía. El único "gráfico de marca" es el
  wordmark contorneado del llamado final (`.cta__mark`).

Si el dashboard cambia de paleta o tipografía, este sitio cambia con él. Si necesitas un color que
no está en `analytics/labels.py`, agrégalo ahí y a `../DESIGN.md` primero.

## 3. Tono y copy

- **Primera persona del producto, no de Cinemex.** El dashboard interno "habla como Cinemex"
  (`AGENTS.md` §2.6); este sitio no — aquí Matiné se dirige a cadenas que **no** son Cinemex.
  Cinemex aparece solo como el piloto que prueba que el producto funciona con datos reales, nunca
  como "nosotros". En las maquetas del tablero, "Tu cadena" va en rojo y "Competencia" en tinta,
  porque eso es lo que esa cadena vería al entrar.
- **Afirmaciones concretas, sin inflar.** Nada de "líder del mercado", "revolucionario",
  "el mejor". Si una frase no se sostiene con lo que el producto hace hoy (un piloto, dos cadenas,
  tres plazas comparables), no se escribe. El piloto se nombra como piloto, no como "cientos de
  clientes".
- **Cero cifras inventadas.** Cualquier número en la página sale de una constante real del repo y se
  anota de dónde: horarios del `Makefile` (07:30, 13:30, 20:30; planos cada hora; sync :22 y :52;
  06:00; 15:00), tipos de cambio y franjas de `analytics/labels.py`, plazas de `scraper/plazas.py`,
  cines por cadena de `project.md` (499 Cinépolis, 278 Cinemex, verificado 2026-09-11). Nunca un
  porcentaje de resultado ("+40 % más ventas"). Si un número del repo cambia, cambia aquí.
- **Español, gramática cuidada**, igual que el resto del repo.
- **Fake door tests, y así se hacen.** Lo que está planeado pero no construido (hoy: la capa narrativa con IA de
  `../project.md` § "Paso 2" y un agente de alertas) **sí** puede aparecer en la página para medir demanda, con tres
  condiciones: se rotula como "Próximamente" o "En evaluación" (`.ai__status`), nunca se describe como disponible ni
  con resultados; su maqueta lo dice en el pie ("no es una salida real"); y cada puerta tiene su **propio CTA** con un
  asunto distinto en el `mailto:` (`door()` en `ai-section.tsx`), que es lo que se cuenta. Sin asunto propio, la puerta
  no mide nada.

## 4. Composición de la portada

La estructura y el lenguaje visual vienen de una referencia editorial (tipografía enorme, hairlines,
numeración, una sección invertida en tinta, un llamado final enmarcado), traducidos a nuestra
marca. Un componente por sección en `components/`, en este orden:

1. **`navigation.tsx`.** Barra fija que al hacer scroll se encoge y flota como tarjeta con borde y
   desenfoque (`.nav--scrolled`). En celular, hamburguesa y menú a pantalla completa con los enlaces
   en display. Un solo botón sólido: "Solicitar acceso".
2. **`hero-section.tsx`.** Rótulo con raya (`.eyebrow`), titular en display de dos líneas con un
   verbo que rota letra a letra ("programa / cancela / mueve / cobra": lo que el producto detecta) y
   un subrayado rojo suave, párrafo + botones en dos columnas, etiqueta "Piloto activo". Al fondo,
   una rejilla tenue y la esfera ASCII (`ascii-sphere.tsx`) en tinta. Al pie, la **cinta** (`.ticker`)
   de cifras reales en marquesina: no son resultados, son lo que el producto mide.
3. **`features-section.tsx`.** "Capacidades": lista numerada `01–04` separada por hairlines, título a la
   izquierda y un SVG animado a la derecha (línea de tiempo, barras al 100 %, corte del día, precios).
   Los SVG van en `currentColor`; la fila de "tu cadena" lleva `.us` (rojo).
4. **`how-it-works-section.tsx`.** Sección invertida en tinta con las tres capas reales del producto
   (`../DESIGN.md` §"Jerarquía en tres capas") como pasos I/II/III que avanzan solos cada 5 s con una
   barra de progreso roja, y una ventana fija (`.win`) con una **maqueta estructural** de cada capa
   (`.mk__*`): barras de esqueleto, sin una sola cifra, con el pie "Estructura ilustrativa".
5. **`ai-section.tsx`.** Fake door de la IA (§3): tres puertas apiladas con hairlines (`.ai__cards`), cada una
   con estado, texto anclado en el diseño real de `project.md` y su CTA rojo con asunto propio; a la derecha,
   ventana fija con la maqueta del resumen en prosa (`.mk__prose`), donde las cifras validadas se marcan en
   rojo suave sin ser cifras. Va después de "Cómo funciona" porque narra lo que esas tres capas producen.
6. **`pilot-section.tsx`.** Cifras grandes a la izquierda (`.stat__*`) y a la derecha el calendario
   diario de captura (`.sched`) con una fila activa que rota, sacado del `Makefile`.
7. **`principles-section.tsx`.** Los seis principios de `AGENTS.md` §2 en una rejilla de hairlines
   (`.hgrid`, 3 × 2), numerados.
8. **`cta-section.tsx`.** Caja con borde de tinta, esquinas decorativas, foco rojo suave que sigue al
   ratón (variables `--mx/--my`, sin hex en el JSX) y el wordmark contorneado. Botón sólido + botón
   fantasma; nota en mayúsculas con el correo.
9. **`footer-section.tsx`.** Marca + dos columnas (Producto, Contacto) + barra inferior. Sin redes
   sociales ni "todos los sistemas operativos": no hay página de estado pública.

**Movimiento.** Toda transición y animación usa la curva `--ease-out` (`cubic-bezier(0.22, 1, 0.36, 1)`), también el
movimiento del mapa de `/a-donde-ir/` (MapLibre recibe esa misma curva, leída de la variable). Las únicas en `linear`
son las continuas o de tiempo: la cinta del hero y la barra de progreso de "Cómo funciona".

Ancho de lectura `--wrap: 1120px`, el mismo que `.block-container` del dashboard; la barra de
navegación llega a 1400 px solo sin scroll. Todo lo que aparece al hacer scroll usa `Reveal` /
`useReveal` (`components/reveal.tsx`, `IntersectionObserver`), y `prefers-reduced-motion` apaga
marquesina, letras, progreso y apariciones.

## 5. Vocabulario del stylesheet (`app/globals.css`)

Un solo archivo, organizado por sección con prefijos BEM. Documentado para que nadie reinvente una
clase con otro nombre para lo mismo:

| Prefijo / clase | Uso |
| --- | --- |
| `.wrap` | Contenedor centrado a `--wrap` |
| `.display`, `.display .muted` | Título de sección en display; segunda línea en gris (o papel al 40 % en la sección oscura) |
| `.eyebrow` | Rótulo en mayúsculas con raya a la izquierda; `.eyebrow--red` cuando es acción |
| `.marca` | Wordmark "Matiné", acento en `--red` |
| `.pill` | Botón píldora; `.pill--primary` (rojo sólido), `.pill--ghost` (borde tinta), `.pill--sm` |
| `.reveal` / `.fade` | Aparición por scroll / al montar; `.is-visible` / `.is-in` la activan |
| `.section` | Franja; `.section--tint` (fondo), `.section--dark` (tinta), `.section--border` |
| `.section-head` | Cabecera de sección; `--split` la parte en dos columnas |
| `.nav__*`, `.nav-overlay` | Barra fija, estado `.nav--scrolled`, menú móvil |
| `.hero__*`, `.char`, `.ticker__*` | Hero, letras animadas del verbo y cinta de cifras |
| `.feat__*` | Filas numeradas de capacidades; `.us` colorea un grupo del SVG en rojo |
| `.how__*`, `.win__*`, `.mk__*` | Pasos de la sección oscura, ventana fija y maqueta estructural |
| `.ai__*`, `.mk__prose*`, `.mk__num`, `.mk__check` | Puertas falsas de la IA y maqueta del resumen narrado |
| `.pilot__*`, `.stat__*`, `.sched__*` | Cifras grandes y calendario de captura |
| `.hgrid__*` | Rejilla con hairlines (gap 1 px sobre `--line`) |
| `.cta__*` | Llamado final enmarcado |
| `.footer__*` | Pie |
| `.demo`, `.demo__*` | `/request-demo/`: a la izquierda qué ofrece la demo; a la derecha, sobre tinta, el formulario en cuatro pasos (correo, datos, cadena, operación) con indicador de pasos |
| `.rec-stage*`, `.rec-dock*`, `.rec-card*`, `.rec-ask*`, `.rec-menu*`, `.rec-screen*`, `.rec-tabs*`, `.rec__*` | `/a-donde-ir/`: pantalla de búsqueda (mapa a pantalla completa con velo, barra que baja al pie, ficha de cine, menú de opciones) y de resultados (pestañas, tabla que en celular se vuelve tarjetas) |

Sin Tailwind ni framework de CSS: las clases son pocas y con nombre, y eso es parte del contrato
con este documento. Si el sitio crece a varias rutas, esa es la señal para reconsiderarlo.

## 6. Qué evitar (patrones que ya vimos fallar en páginas genéricas)

- **El héroe con blob de gradiente morado-azul.** No es la marca; color plano y el trío
  rojo–tinta–blanco de `../DESIGN.md`. La esfera ASCII es tinta al 35 %, nunca un color nuevo.
- **Logos de clientes falsos, testimonios o precios inventados.** La referencia los traía; aquí no
  hay ninguno porque no existen. Hay un piloto con un nombre real (Cinemex) y se nombra tal cual.
- **"Métricas en vivo" que no lo son.** Ni reloj ni punto verde de "todo operativo": esta página es
  estática y no ve la operación. El punto rojo de "Piloto activo" es una etiqueta, no un estado.
- **Captura del dashboard con números que parezcan reales.** Las maquetas de la ventana son
  esqueletos (`.mk__line`) y lo dicen en su pie. Nunca una captura real ni una cifra que se pueda
  confundir con una métrica medida.
- **Tarjetas de "features" genéricas.** Cada fila de capacidades y cada celda de metodología señala a
  algo que el repo implementa (`scraper/diff.py`, `analytics/`, `from_now`, `cinema_week`); las puertas
  falsas de IA señalan a un diseño escrito (`project.md` § "Paso 2") y lo dicen. "IA" a secas, sin decir
  qué hace ni qué no hace (redacta, no calcula), es la versión genérica que no queremos.
- **Formulario con backend.** El formulario de `/request-demo/` (`components/demo-form.tsx`) no envía a un servidor:
  abre el correo del visitante con la solicitud escrita, a `CONTACT_EMAIL` (`lib/site.ts`). El correo es un marcador
  hasta que exista la bandeja real.

## 7. `/a-donde-ir/`: demo pública del recomendador

`app/a-donde-ir/page.tsx` + `components/recommender.tsx` (formulario, resultados) + `components/recommender-map.tsx`
(mapa) + `lib/recommend.ts` (cálculo en el navegador). El visitante da su punto de partida (dirección, ubicación del
navegador o doble clic en el mapa), su grupo (adultos, niños, adultos mayores), un paquete de dulcería, su presupuesto y el
día; ve las funciones que le quedan cerca y caben.

- **Tres ciudades** (2026-09-27): CDMX, Guadalajara y Monterrey van en el mismo catálogo (`plazas`, con el centro y la
  caja de sus cines). Sin punto de partida, tres chips bajo la barra (`.rec-stage__cities`, los mismos `.rec__chip`)
  eligen la ciudad: mueven el mapa de fondo y acotan el buscador y su caché a esa zona. Con punto de partida, la ciudad
  es la más cercana a él y los chips desaparecen.

- **Datos** (2026-09-28). La API pública (`../api/main.py`) responde cada búsqueda con la lógica de precios del
  dashboard (`../analytics/recommender.py`). La página nunca recibe el catálogo completo. `NEXT_PUBLIC_API_URL` fija
  la dirección al construir; en local es `http://localhost:8000`. `lib/api.ts` pide `opciones` al cargar: ciudades,
  días, formatos, cines para las sugerencias y la hora de la captura. Pide `funciones` 250 ms después del último
  cambio del plan y cancela la consulta anterior. Desde el 2026-09-29 la API solo ofrece hoy y mañana y responde
  hasta 120 funciones por pestaña y 6 por cine, para que una búsqueda amplia muestre más cines; la tabla pinta 20 por
  página (`PAGE`) y "Ver N más" agrega otras 20. El selector de días sale de `opciones.dates`, así que muestra dos. La ficha de un edificio pide `funciones?sitio=lat,lng`. Si la API
  falla o limita (429), la barra lo dice en palabras.
- **Neutral entre cadenas** (decisión 2026-09-27): a diferencia del dashboard, aquí no se destaca a Cinemex. Los
  cines van todos en tinta, sin color por cadena, y un empate se resuelve por distancia y hora. El único rojo es la
  acción: el botón Buscar, los rótulos de los pasos y el punto de partida.
- **Sin cifras inventadas.** Una función sin precio de su cine va aparte ("sin precio de boletos"); si el grupo pide
  dulcería y el cine no publica su menú en sala (Cinemex, la Cineteca), la función va en "Sin precio de dulcería en
  sala" con solo los boletos. Sin paquete, la columna Dulcería muestra la referencia de palomitas y refresco donde
  existe.
- **Mapa.** MapLibre (`maplibre-gl`, la única dependencia nueva) con el estilo Positron de OpenFreeMap: sin clave,
  uso comercial permitido. Sin WebGL, el mapa se reemplaza por un aviso y el resto sigue funcionando. Un clic en un cine abre su ficha; un clic suelto en otro
  lugar no hace nada, porque puede ser accidental. El doble clic (o doble toque) mueve el punto de partida; el zoom con
  doble clic está apagado. Un punto por edificio: el complejo y su sala Platino
  o VIP comparten coordenadas (31 lugares en las tres plazas, 2026-09-27). La ficha muestra las funciones de todos sus
  cines y, si hay más de uno, el nombre del cine en cada función.
- **Direcciones, con sugerencias mientras se escribe** (2026-09-27). Tres capas, para que una red lenta no se note:
  1. *Índice local* (`/lugares.json`, versionado; `make export-places` → `../scripts/export_places.py`): unos 6 mil
     lugares de las tres ciudades de OpenStreetMap (colonias, alcaldías, ciudades, estaciones de Metro, Metrobús, Tren
     Ligero, Cablebús, Mi Macro, Metrorrey y Ecovía, plazas comerciales, universidades) más los cines del catálogo;
     88 KB comprimido. A igual coincidencia gana lo más cercano a la ciudad elegida. Se busca en el navegador
     (`lib/places.ts`): cada palabra escrita debe iniciar una palabra del nombre, sin acentos ni mayúsculas; primero lo
     que empieza igual, luego por tipo (alcaldía y colonia antes que universidad) y cercanía. Desde 2 letras, en ~15 ms.
  2. *Photon* (komoot, datos de OSM, sin clave) solo si lo local no llena 3 sugerencias o si hay un número (una calle
     con número): desde 3 letras y tras 250 ms sin teclear, dentro de la zona de la ciudad elegida y cerca del punto actual,
     `lang=default` (con `lang=es` no responde). Nominatim, el buscador nativo de OSM, prohíbe autocompletar.
  3. *Caché*: cada respuesta de Photon se guarda por ciudad y texto en memoria y en `localStorage` (las últimas 60); mientras
     llega una nueva se filtra la del texto guardado más largo que empiece igual. `preconnect` abre la conexión con
     Photon al cargar, para ahorrar el saludo TLS de la primera búsqueda.
  Nombre en tinta y contexto en gris (el tipo, salvo que el nombre ya lo diga); clic, ↑↓ + Enter o Esc; enviar sin
  elegir toma la primera. Con tráfico real, cambiar Photon por una instancia propia o un proveedor con clave es cambiar
  `geocode()` en `components/recommender.tsx`. Crédito a OpenStreetMap en el pie. La ubicación del navegador pide
  HTTPS (o localhost).
- **Compartir.** `?lat=…&lng=…` en la URL abre la página con ese punto de partida.
- **Comprar** (2026-09-27). Cada función lleva "Comprar ↗" (`.rec__buy`, rojo porque es la acción) bajo la hora, en la
  tabla y en la ficha del cine. Abre en otra pestaña el sitio de la cadena con las plantillas de
  `../scraper/config.py` (`BUY_URL`): Cinemex en la página del cine con la película y el día filtrados; Cinépolis en
  el paso "Horario" con el cine y la película elegidos. No hay enlace a la función exacta. La Cineteca no lleva
  enlace.
- **Celular.** Debajo de 700 px cada función es una tarjeta con el cine y el total arriba (`.rec__c-*`).

- **Estructura: una pantalla por cosa** (2026-09-27, a pedido de David; fondo papel y reglas de `../DESIGN.md`: sin
  sombras, radio 8 px en tarjetas, píldora solo en controles). Nada se lee haciendo scroll por toda la página:
  1. *Búsqueda*: el mapa llena la pantalla bajo el nav. Sin punto de partida, un velo de papel al 70 % con desenfoque
     lo deja como fondo apenas visible y no recibe clics; al centro, el título y una sola barra en píldora (opciones ·
     dirección · mi ubicación · buscar en rojo). Con punto de partida el velo se desvanece, el mapa se vuelve
     interactivo y la barra baja al pie con una transición (el "dock", como un chat): encima de ella, una línea con el
     plan y el botón rojo "Ver funciones en N cines". Los cines que tienen funciones que caben son puntos en tinta;
     tocar uno lo agranda y abre su ficha flotante (todas sus funciones que caben, por hora, con total); tocar fuera
     de un cine mueve el punto de partida. El crédito del mapa va arriba a la izquierda. El botón de opciones abre un
     menú con quiénes van, dulcería, cuándo, presupuesto y más filtros (hacia abajo con la barra al centro, hacia
     arriba con la barra al pie): cada fila es una línea (ícono, qué y su valor en gris) que al tocarla muestra sus
     controles y una ×; se cierra con un clic afuera o Esc.
  2. *Resultados*: "← Cambiar búsqueda" con el plan en una línea, el resumen y pestañas (Caben, Sin precio de dulcería,
     Sin precio de boletos, cada una con su total) en vez de secciones apiladas; 10 funciones a la vez con "Ver más".

Clases: `.rec-stage*` (pantalla de búsqueda: mapa, velo, título), `.rec-dock*` (barra al centro o al pie),
`.rec-card*` (ficha de un cine), `.rec-ask*` (barra), `.rec-menu*` (menú de opciones), `.rec-screen*` y
`.rec-tabs*` (pantalla de resultados), `.rec__*` (contador, fichas, campos, tabla y tarjetas de resultados).

## 8. Verificar un cambio

```sh
cd marketing
npm install     # una vez
npm run dev     # http://localhost:3000
npm run build   # genera marketing/out; falla si hay errores de tipos o de export estático
node --experimental-strip-types --test lib/demo.test.mjs   # reglas del formulario de /request-demo/

# Capturas con el Chrome instalado, a un viewport exacto (el flag --screenshot de Chrome no
# respeta anchos menores a ~500 px ni espera a las animaciones):
node scripts/screenshot.mjs http://localhost:3000/ 1440 900 /tmp/hero.png
node scripts/screenshot.mjs http://localhost:3000/ 390 844 /tmp/movil.png full
```

No hay pruebas automatizadas del sitio; el cálculo de precios de `/a-donde-ir/` se prueba del lado de Python
(`../tests/test_recommend.py`, incluido el formato del JSON). Para `/a-donde-ir/`, captura con un punto de partida:
`node scripts/screenshot.mjs "http://localhost:3000/a-donde-ir/?lat=19.35&lng=-99.162" 1440 900 /tmp/rec.png full`
(el script activa WebGL por software para que se dibuje el mapa). Antes de dar por bueno un cambio de copy
o de sección, mira la página entera en escritorio (1440) y en celular (390): la cinta del hero debe
quedar dentro del primer viewport en 1440 × 900, la ventana de la sección oscura debe verse completa,
y las rejillas (`.feat__body`, `.hgrid`, `.pilot__grid`, `.cta__inner`) deben apilarse sin desbordar.
