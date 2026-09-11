# Guía de Diseño

Referencia visual para todo lo que se presente al cliente (Cinemex): dashboard Streamlit, gráficas Altair, reportes y capturas. Cinemex es la marca protagonista y va en rojo; Cinépolis es el competidor y va en tinta (casi negro), nunca en rojo. La estructura de la página es la jerarquía en tres capas del mockup del 2026-09-08.

## Paleta de colores

Adoptada el 2026-09-08 con el mockup "Propuesta de jerarquía en 3 capas". Sustituye al rojo `#FF1744` y al
gris `#333333` de la primera versión.

### Tokens

| Token | Hex | Uso |
|---|---|---|
| `--red` | `#E31837` | Cinemex: serie en gráficas, acento del encabezado, borde izquierdo de los hallazgos, chips "Decisión" |
| `--red-soft` | `#FDEDF0` | Fondo de chips y hover de botones y navegación |
| `--red-dark` | `#9E0F26` | Primer tono de la rampa ordinal (Premium / VIP) |
| `--ink` | `#191A1E` | Texto fuerte, Cinépolis en gráficas, rótulos "CAPA", bloque "Qué se desbloquea" |
| `--gris` | `#5C6068` | Texto secundario, ejes y leyendas |
| `--linea` | `#E4E5E9` | Bordes de tarjetas y divisores de tabla |
| `--papel` | `#FFFFFF` | Tarjetas y secciones |
| `--fondo` | `#F6F6F4` | Fondo de página y bloque de conclusión |
| `--ok` | `#2F6F4E` | Chip de estado sano. **Solo en la página Operaciones** (admin) |
| `--warn` | `#B45309` | Chip y celdas de estado con problema, corridas fallidas. **Solo en la página Operaciones**; el rojo sigue siendo Cinemex |

### Reglas de uso

- **Rojo solo para Cinemex y para acción.** Un rojo en pantalla significa "Cinemex" o "decisión / haz clic". No se usa
  para alertas ni para valores negativos.
- **Cinépolis en tinta.** En comparativas, Cinépolis va en `#191A1E` (barras, puntos) y sus cifras en negro; las de
  Cinemex pueden ir en rojo. El rojo domina sin competir.
- **Contraste alto.** Texto blanco sobre rojo o tinta; texto `#191A1E` sobre blanco o `#F6F6F4`. Gris `#5C6068` solo
  para texto secundario de 13 px o más.
- **Rampa ordinal** (cubetas ordenadas de formato) a partir del rojo: `#9E0F26`, `#E31837`, `#F08497`, `#F7CDD5`.
- **Divergente** (mapa de calor de Δ pp): lado Cinemex en rojo (`#F6B7C2` → `#E31837`), lado Cinépolis en tinta
  (`#8C8E95` → `#191A1E`), centro `#EFEFEF`. Texto blanco cuando la celda es oscura o saturada.

## Tipografía

Una sola familia: **Archivo** (variable, Google Fonts), con el eje de anchura para los títulos. Sans-serif del sistema
como respaldo.

| Elemento | Peso | Anchura (`font-stretch`) | Tamaño |
|---|---|---|---|
| H1 (encabezado) | 850 | 75 % | 30–46 px, `line-height` 1.02 |
| H2 (título de capa) | 800 | 80 % | 26 px |
| Pregunta de sección | 800 | 82 % | 22 px |
| Titular de hallazgo | 750 | 100 % | 19 px |
| Conclusión | 700 | 100 % | 15.5 px |
| Cuerpo | 400–500 | 100 % | 15 px, `line-height` 1.55 |
| Notas, soporte, tablas | 400–600 | 100 % | 12.5–13.5 px, números tabulares |

## Jerarquía en tres capas

La página se lee de arriba abajo con costo de atención decreciente:

1. **Capa 1, "Lo que importa hoy".** Hasta tres hallazgos redactados como decisión (titular, una línea de contexto,
   chip "Decisión: …") con cuatro a seis números de soporte a la derecha. Vienen de `analytics.findings`; si ninguna
   diferencia cruza su umbral, la capa lo dice y no inventa.
2. **Capa 2, "Evidencia por pregunta".** Una sección blanca por pregunta de negocio: la pregunta, la conclusión en un
   bloque con borde izquierdo de tinta, el gráfico como prueba y la guía "Cómo leerla" colapsada.
3. **Capa 3, "Detalle y apéndice".** Todo colapsado con una línea de resumen en gris al lado del título. Cierra con el
   bloque oscuro "Qué se desbloquea con tus datos", que convierte cada panel pendiente en un argumento (qué decisión
   habilita, cuándo estará listo).

## Componentes

### Encabezado

Título con la palabra "Cinemex" en rojo, borde inferior de 3 px en tinta, fila de metadatos (periodo, cines,
funciones, última captura) y navegación en píldora con borde de tinta a las tres capas.

### Rótulos de capa

Etiqueta "CAPA N" en caja (roja para la Capa 1, tinta para las demás), H2 a su derecha y una línea de descripción en
gris de hasta 640 px.

### Tarjeta de hallazgo

Fondo blanco, borde `#E4E5E9`, borde izquierdo de 5 px rojo, radio 6 px, padding 20 × 24 px. Rejilla de dos columnas:
texto y columna de soporte (240 px, separada por una línea) con pares etiqueta / valor en negrita; valores de Cinemex en
rojo. En pantallas angostas la columna pasa abajo.

### Sección de evidencia

Fondo blanco, borde `#E4E5E9`, radio 6 px, padding 22 × 26 px. Orden fijo: pregunta, conclusión (fondo `#F6F6F4`, borde
izquierdo 3 px tinta, negrita, con la nota en cursiva gris), leyenda, gráfico, controles, "Cómo leerla".

### Apéndice

`st.expander` estilizado: fondo blanco, borde, radio 6 px, chevrón rojo. La etiqueta lleva el título y, en gris, una
línea de resumen con las cifras clave para que no haga falta abrirlo.

### Botones y controles

Secundarios en píldora (radio 999 px), borde 1.5 px tinta, texto tinta, hover `#FDEDF0`. No hay botones rojos
rellenos en el dashboard: el rojo se reserva para Cinemex y los chips de decisión.

### Formularios y tarjeta de acceso

Las páginas sin sesión (entrar, olvidé mi contraseña, restablecer) usan una sola tarjeta centrada de ancho medio
(columna central de tres, ~1/3 del ancho), fondo blanco, borde `#E4E5E9`, radio 6 px, padding 30 × 32 px, con la marca
"Absolut Cinema" condensada (la segunda palabra en rojo), un encabezado corto y una línea de contexto en gris. Los campos
son los del tema (borde `#E4E5E9`, foco rojo) y el botón de envío es la píldora secundaria de siempre; no hay botón rojo
relleno ni en el login. Los errores usan `st.error` con los textos de `AUTH_TEXT`; nunca se revela si un correo existe.
Al entrar o salir la página se recarga completa (≈1 s): es lo que exige la cookie en Streamlit.

### Barra de cuenta

Con sesión, la barra lateral abre con "Sesión de **Nombre**", correo y rol en gris (`.cuenta`) y el botón píldora
"Cerrar sesión", seguido de un divisor; debajo van los filtros de la página. La página Usuarios reutiliza la sección de
evidencia (`seccion`) para los dos bloques (nueva cuenta, administrar una cuenta) y la tabla estándar para la lista. El
explorador Datos usa `st.dataframe` a 560 px de alto con orden y búsqueda nativos, precios con formato `$`, y un botón
de descarga CSV.

### Tablas

Compactas, sin fondo en el encabezado: cabecera en gris con borde inferior 1.5 px, filas separadas por 1 px
`#E4E5E9`, números tabulares alineados a la derecha, la columna de Cinemex en rojo y la de Cinépolis en negrita.

### Gráficas (Altair)

- Serie Cinemex `#E31837`, serie Cinépolis `#191A1E`; la barra del dumbbell en `#C9CBD0`.
- Fuente Archivo, ejes y leyendas en gris `#5C6068`, rejilla `#ECEDEF`, sin marco ni ticks.
- Mapa de calor: celdas con radio 4 px separadas por 4 px de blanco, sin leyenda de color (el número va en la celda).
- Barras apiladas al 100 %: rampa ordinal roja, etiqueta de la cadena coloreada (Cinemex rojo, Cinépolis tinta).

## Estilo visual

- **Editorial, no de panel de control.** Titulares condensados y contundentes, mucho blanco, una sola familia.
- **Contraste.** Rojo + tinta + blanco como trío principal; el gris solo acompaña.
- **Espaciado.** Las capas respiran (44 px entre rótulos); las tarjetas 14–18 px entre sí.
- **Bordes.** Radio 4–8 px en tarjetas; píldora solo en navegación y botones.
- **Sin sombras.** La jerarquía la dan el borde, el color y el tamaño del texto.

## Aplicación en este repo

- **Tema Streamlit.** El bloque `[theme]` de `.streamlit/config.toml` fija colores, radios, la familia Archivo y los
  pesos de encabezado. Fondo de página `#F6F6F4`, fondo secundario blanco (tarjetas, barra lateral).
- **Constantes de color.** Viven en `analytics/labels.py`: `RED`, `RED_DARK`, `RED_SOFT`, `INK`, `GRAY`, `GRAY_DARK`,
  `GRAY_LIGHT`, `LINE`, `PAPER`, `NEUTRAL`, `GRID`, `CHAIN_COLOR`, `RED_RAMP`, `DIVERGING`, y los de estado `OK` y `WARN`
  (solo Operaciones). Ningún hex se escribe
  directo en la presentación salvo tonos internos del bloque oscuro de desbloqueo.
- **CSS complementario.** `ui/common.py` (`inject_css`, llamado desde `app.py`) inyecta la fuente variable Archivo desde Google Fonts, el ancho de lectura
  (1120 px) y los componentes del mockup: `.enc`, `.capa-tag`, `.hallazgo`, `.pregunta`, `.conclusion`, `table.mk`,
  `.desbloqueo`, `.marca`, `.acceso-h`, `.acceso-lead`, `.cuenta`; y estiliza los expanders según su contenedor
  (`st-key-apendice-*`, `st-key-leerla-*`), las secciones (`st-key-sec-*`) y la tarjeta de acceso (`st-key-acceso`).
- **Textos.** Los hallazgos y las conclusiones salen de `analytics/findings.py`; las etiquetas de `analytics/labels.py`.

Para un color nuevo, agregarlo a `analytics/labels.py` y documentarlo aquí antes de usarlo.

### Página Operaciones (solo admin)

Tablero de lectura para ingeniería, no para el cliente: reutiliza las secciones (`st-key-sec-*`), `table.mk`, el bloque
oscuro de pendientes y la cola de logs en `st.code`. Es la única página con nombres internos a la vista (tablas, logs) y
con los colores de estado `OK`/`WARN` (chip `.estado`, celdas `td.mal`). La gráfica de corridas mantiene las cadenas en
sus colores y marca las fallidas con una cruz ámbar.

### Navegación entre páginas

`st.navigation(position="top")`: pestañas "Cartelera", "Dulcería", "Datos" y, para el rol admin, "Usuarios" y "Operaciones" en la barra
superior en escritorio. Sin sesión la navegación va oculta (`position="hidden"`) y solo existen las páginas de acceso. En pantallas de
768 px o menos, una regla `@media` fija la barra al pie de la pantalla (fondo papel, borde superior, sombra suave) y
deja 84 px de aire al final del contenido, para que quede al alcance del pulgar. No probado en dispositivo real
(Streamlit colapsa los enlaces en un desplegable si no caben).
