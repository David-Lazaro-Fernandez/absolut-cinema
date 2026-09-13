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

No es un blog, no tiene rutas más allá de la portada, y no necesita servidor: es contenido
estático (`next.config.mjs` usa `output: 'export'`).

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
- **Formulario con backend.** El CTA es un `mailto:` (`lib/site.ts`); el correo es un marcador hasta
  que exista la bandeja real.

## 7. Verificar un cambio

```sh
cd marketing
npm install     # una vez
npm run dev     # http://localhost:3000
npm run build   # genera marketing/out; falla si hay errores de tipos o de export estático

# Capturas con el Chrome instalado, a un viewport exacto (el flag --screenshot de Chrome no
# respeta anchos menores a ~500 px ni espera a las animaciones):
node scripts/screenshot.mjs http://localhost:3000/ 1440 900 /tmp/hero.png
node scripts/screenshot.mjs http://localhost:3000/ 390 844 /tmp/movil.png full
```

No hay pruebas automatizadas: es una sola página estática. Antes de dar por bueno un cambio de copy
o de sección, mira la página entera en escritorio (1440) y en celular (390): la cinta del hero debe
quedar dentro del primer viewport en 1440 × 900, la ventana de la sección oscura debe verse completa,
y las rejillas (`.feat__body`, `.hgrid`, `.pilot__grid`, `.cta__inner`) deben apilarse sin desbordar.
