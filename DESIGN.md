# Guía de Diseño Cinemex

Referencia visual para todo lo que se presente al cliente (Cinemex): dashboard Streamlit, gráficas Altair, reportes y capturas. Cinemex es la marca protagonista; Cinépolis es el competidor y se muestra en un tono neutro o secundario, nunca en rojo.

## Paleta de colores

### Primarios

| Token | Hex | RGB | Uso |
|---|---|---|---|
| `--cmx-red` | `#FF1744` | 255, 23, 68 | CTA, headers, elementos destacados, serie "Cinemex" en gráficas |
| `--cmx-white` | `#FFFFFF` | 255, 255, 255 | Fondo principal, texto sobre rojo |
| `--cmx-black` | `#000000` | 0, 0, 0 | Texto secundario, divisores |

Variante alterna del rojo aceptada por la marca: `#FF0040`. Usar una sola en todo el proyecto; la canónica aquí es `#FF1744`.

### Secundarios

| Token | Hex | Uso |
|---|---|---|
| `--cmx-red-dark` | `#C41C3B` | Hover y estados activos de botones rojos |
| `--cmx-gray-light` | `#F5F5F5` | Fondos alternativos, filas alternas, tarjetas de contexto |
| `--cmx-gray-dark` | `#333333` | Texto principal sobre fondos claros |

### Reglas de uso

- **Rojo solo para Cinemex y para acción.** Un rojo en pantalla debe significar "Cinemex" o "haz clic aquí". No usarlo para alertas ni para valores negativos; para eso conviene un neutro oscuro o texto.
- **Cinépolis en neutro.** En comparativas, Cinépolis va en gris (`#333333` en barras, `#B8B7B1` para líneas de referencia) para que el rojo de Cinemex domine sin competir.
- **Contraste alto.** Texto blanco sobre `#FF1744` y texto `#333333` sobre blanco o `#F5F5F5`. Evitar gris sobre gris.
- **Rampas ordinales** (cubetas ordenadas, mapas de calor) se construyen a partir del rojo: `#C41C3B`, `#FF1744`, `#FF6B86`, `#FFC2CE`. Para divergentes, el lado Cinemex es rojo y el lado Cinépolis es gris oscuro, con `#F0EFEC` como centro.

## Tipografía

### Familias

| Rol | Familia sugerida | Alternativas |
|---|---|---|
| Headings | Montserrat Bold | Bebas Neue, Poppins Bold |
| Cuerpo | Inter | Poppins, Roboto |
| Énfasis | Montserrat Extra Bold | Poppins Extra Bold |

Todo sans-serif. Si la plataforma no permite cargar fuentes (Streamlit sin CSS custom), se acepta la sans-serif del sistema respetando los pesos de abajo.

### Pesos

| Elemento | Peso |
|---|---|
| H1 | 700–900 |
| H2 | 700–800 |
| Cuerpo | 400–500 |
| Botones | 600–700 |

### Escala sugerida

| Elemento | Tamaño |
|---|---|
| H1 | 32–40 px |
| H2 | 24–28 px |
| H3 | 18–20 px |
| Cuerpo | 14–16 px |
| Caption / notas | 12–13 px |

## Componentes

### Botones

- **Primario.** Fondo `#FF1744`, texto blanco, peso 600–700, radio 6 px. Hover `#C41C3B`; active un tono más oscuro (`#9E1530`).
- **Secundario.** Borde 2 px `#FF1744`, fondo transparente, texto `#FF1744`. Hover: fondo `#FF1744` al 8 % de opacidad.
- **Deshabilitado.** Fondo `#F5F5F5`, texto `#B8B7B1`, sin sombra.

### Tarjetas

- Fondo blanco con sombra leve (`0 2px 8px rgba(0,0,0,0.08)`).
- Borde superior rojo de 3–4 px.
- Padding interno generoso: 20–24 px.
- Radio 6–8 px.

### Métricas / KPIs

- Valor en H2 con peso 800, color `#333333`.
- Etiqueta en caption, `#333333` al 70 %.
- Si la métrica es de Cinemex, el valor puede ir en `#FF1744`; la de Cinépolis siempre en `#333333`.

### Promociones y destacados

- Fondo `#FF1744` con texto blanco grande (H1 o H2, peso 800–900).
- Contraste alto; nada de texto gris sobre rojo.
- Iconografía y elementos visuales (palomitas, bebidas) en blanco plano.

### Tablas

- Encabezado con fondo `#F5F5F5`, texto `#333333` peso 600.
- Filas alternas blanco / `#F5F5F5`.
- Divisores en `#000000` al 10 %.

### Gráficas (Altair)

- Serie Cinemex: `#FF1744`. Serie Cinépolis: `#333333`.
- Líneas de referencia y ejes: `#B8B7B1`.
- Fondo del gráfico blanco; sin grid vertical, grid horizontal muy tenue.
- Etiquetas de datos dentro de barras en blanco, peso bold; fuera de barras en `#333333`.
- Esquinas de barras: 2–3 px.

## Estilo visual

- **Energía.** Audaz, moderno, dinámico. Títulos grandes y contundentes.
- **Contraste.** Alto, siempre rojo + blanco como pareja principal.
- **Espaciado.** Generoso; las secciones respiran. Separación mínima entre bloques: 32 px.
- **Bordes.** Redondeados suaves, 4–8 px. Nunca completamente cuadrados ni tipo píldora.
- **Sombras.** Leves y difusas; nada de sombras duras.

## Aplicación en este repo

- **Tema Streamlit.** El bloque `[theme]` de `.streamlit/config.toml` fija colores, radios de 6 px, familias tipográficas (Inter para cuerpo, Montserrat para títulos), pesos de encabezados y las paletas categórica y secuencial de las gráficas.
- **Constantes de color.** Viven en `analytics/labels.py`: `RED`, `RED_DARK`, `GRAY_DARK`, `GRAY_LIGHT`, `NEUTRAL`, `CHAIN_COLOR` (Cinemex rojo, Cinépolis gris oscuro), `RED_RAMP` (ordinal) y `DIVERGING` (gris ↔ rojo). Ningún hex se escribe directo en `app.py`.
- **CSS complementario.** `app.py` inyecta solo lo que el tema no cubre: carga de fuentes desde Google Fonts, borde superior rojo y sombra en las tarjetas (contenedores creados con `card()`, cuya key empieza por `card-`), pesos de H1–H3 y hover de botones.
- **Gráficas.** Cinemex siempre en `CHAIN_COLOR["cinemex"]` y Cinépolis en `CHAIN_COLOR["cinepolis"]`; separadores de barras y celdas en blanco; texto de datos en blanco sobre tonos oscuros y en `GRAY_DARK` sobre tonos claros.

Para un color nuevo, agregarlo a `analytics/labels.py` y documentarlo aquí antes de usarlo.
