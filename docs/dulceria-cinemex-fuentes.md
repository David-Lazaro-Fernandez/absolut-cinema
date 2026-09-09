# Precios de dulcería de Cinemex: fuentes en línea (investigación 2026-09-09)

Informe de un agente de búsqueda web lanzado el 2026-09-09. Todas las URLs fueron abiertas o aparecieron en
resultados de búsqueda. Complementa la sección "Dulcería" de `project.md`.

## Veredicto

Sí existe una fuente repetible: Cinemex vende dulcería a domicilio en **Uber Eats, Rappi y DiDi Food** con ~20 SKUs
por sucursal (combos, Mega Palomitas, hot dog, nachos, refrescos en lata, chapatas) y las tres plataformas entregan
los precios en HTML/JSON renderizado del lado del servidor, sin login ni geolocalización. La mejor es Uber Eats
(endpoint JSON interno `POST /_p/api/getStoreV1`, respondió sin autenticación con precios en centavos), con Rappi
(`__NEXT_DATA__`) como respaldo. Limitaciones: el catálogo de delivery es un subconjunto "para llevar" (Mega
Palomitas 230 g, latas 355 ml) y **no incluye los tamaños chico/mediano/grande ni los refrescos de máquina del
tablero en sala**; el precio es **idéntico en las 15 sucursales comparadas** (CDMX, Edomex, GDL, Zacatecas,
Querétaro): lista nacional, no por cine.

## Fuentes

| Fuente | URL | Qué tiene | Extraíble | Riesgo |
| --- | --- | --- | --- | --- |
| Uber Eats, tiendas Cinemex | `https://www.ubereats.com/mx/store/cinemex-galerias/BSheBEirWpWoFyahoWhOKQ`, `…/cinemex-universidad/BuruAf9WQ4CHFvKk3XrUaw`, `…/cinemex-real/fI0OLiDmUQG2Skbn3H4g4A` (12 sucursales CDMX vistas) | 17–21 SKUs con precio, gramaje, dirección, horario 13:00–21:00; precio nacional | Sí: `application/ld+json` (Restaurant → hasMenu → offers.price) y `POST https://www.ubereats.com/_p/api/getStoreV1?localeCode=mx` con body `{"storeUuid":"…","diningMode":"DELIVERY"}` y header `x-csrf-token: x` | **Alto**: los Términos de Uso de Uber México prohíben scripts de extracción y uso no personal/comercial. robots.txt no bloquea |
| Rappi, tiendas Cinemex | Listado CDMX `https://www.rappi.com.mx/ciudad-de-mexico/restaurantes/delivery/51760-cinemex` (35 IDs); ej. `https://www.rappi.com.mx/restaurantes/1923249458-cinemex` | Mismos SKUs y precios; `status`, `isCurrentlyAvailable` | Sí: `__NEXT_DATA__` → `props.pageProps.fallback` (store + productos `id, name, price, description`). 2 de 6 tiendas sin productos | T&C sin cláusula anti-scraping explícita; robots sin bloqueo |
| DiDi Food, tiendas Cinemex | `https://web.didiglobal.com/mx/food/ciudad-de-mexico-cdmx/cinemex-galerias/5764607533952794847/` (9 CDMX vistas) | Mismos SKUs; horario 12:00–22:00 | Sí: HTML estático, bloques `<h4>nombre</h4> … <span>MX$150.00</span> <p>descripción</p>`; parsear por bloque | **El de menor riesgo**: T&C sin cláusula anti-scraping, robots `Allow: /` |
| Uber Eats / Rappi, Cinépolis (paridad) | `https://www.ubereats.com/mx/store/cinepolis-encuentro-fortuna/kp_hyhaoQHaXMRZ61VUfEA`; `https://www.rappi.com.mx/restaurantes/1923302272-cinepolis-tradicional` | 34 SKUs: combos, dulces, helados, 600 ml; precios distintos a los de sala | Sí, mismos mecanismos | Igual |
| cinemex.com/promociones | `https://cinemex.com/promociones` | JSON embebido con 19 promos (título, url, imagen) **sin precios**; bases en `api.cinemex.com/rest/v2.2/landings/{slug}` y `/rest/v2.2/promos/`, que respondieron `app-update-required` sin headers de app | Parcial; probar con los headers del scraper | Bajo |
| X @Cinemex | `https://syndication.twitter.com/srv/timeline-profile/screen-name/Cinemex` (106 tuits) | Anuncios de Cinemex Manía; precio solo en imagen (OCR) | Parcial | ToS de X |
| Prensa | Telediario 24-mar-2026 y 5-abr-2026, El Informador 14-ene-2026, La Silla Rota 11-feb-2025, SDP 4-abr-2025, El Universal ene-2025, Merca2.0 ago-2024, Diegetico ene-2025 | Precios de combos en sala, nacionales, sin cine | No (editorial) | — |
| PriceListo | `https://mx.pricelisto.com/menu-prices/cinemex-mx` | 15+ SKUs iguales al catálogo de delivery, "actualizado 15 dic 2025" | Parcial (agregador) | Segunda mano |
| menucine, menu-precios, allmenuprecios, mxmenu | — | Precios inventados o convertidos de USD | No | No confiable |
| PROFECO | — | No hay levantamiento de dulcería de cines | — | — |

## Precios concretos

Delivery, en vivo el 2026-09-09, idénticos en las tres plataformas y en 15 sucursales:

| Producto | Cinemex | Cinépolis |
| --- | --- | --- |
| Combo tradicional (palomitas + 2 refrescos) | 150 (Mega Clásicas 230 g + 2 latas) | 187 ("Palomitas Cinépolis & Refresco"), 276 (Combo Palomitas) |
| Combo Nachos | 195 | 273 (chicos) |
| Combo Hot Dog | 245 | 330–346 (con dulce o helado) |
| Palomitas solas | 104 (Mega Clásicas), 134 (sabor) | — |
| Hot Dog | 58 | 102 |
| Nachos con queso | 65 | 124 |
| Refresco | 29 (lata 355 ml) | 44 (600 ml) |
| Extra queso | 22 | 27 |
| Chapatas | 90–105 | — |
| Dulces (M&M's, Skittles, Skwinkles) | — | 89–95 |

Prensa, precios en sala, nacionales:

| Producto | Precio | Fuente y fecha |
| --- | --- | --- |
| Combo Individual Cinemex (palomitas grandes + refresco grande) | 129 | Telediario abr-2026; Merca2.0 ago-2024 |
| Combo Nachos / Combo Hot Dog / Combo Pareja Cinemex | 195 / 245 / 272 | Telediario abr-2026 |
| Lunes de Combo Cinemex (2 boletos + palomitas + 2 refrescos) | 215 | Telediario abr-2026; La Silla Rota feb-2025 |
| Combo Palomera Scream 7 Tradicional / Market | 640 / 660 | Telediario mar-2026 |
| Cinemex Manía ene-2026 individual / pareja | 135 / 210 | El Informador ene-2026 |
| Cinemex Manía abr-2025 individual / pareja | 110 / 195 | SDP abr-2025 |
| Palomitas Cinemex mediana / grande / mega (mantequilla) | 79 / 84 / 120 | Telediario ago-2024 |
| Mega Palomitas Clásicas (app Cinemex) | 99 ene-2025 → 104 hoy | Diegetico; delivery |
| Combo Cuates Cinépolis | 175 (2023) → 271 (2025) | La Silla Rota feb-2025 |
| Combo Ice Cinépolis / Cinemex | 333 / 300 | La Silla Rota feb-2025 |

## Recomendación técnica del agente

1. Fuente primaria Uber Eats `getStoreV1` (storeUuid en el HTML; respuesta en `data.catalogSectionsMap[…][].payload.standardItemsPayload.catalogItems[]` con `title`, `price` en centavos, `isSoldOut`), o el `ld+json` de la tienda como alternativa más estable. Obstáculo: ToS de Uber prohíbe extracción.
2. Respaldo Rappi `__NEXT_DATA__`; tercera verificación DiDi Food (menor riesgo legal, HTML menos estructurado).
3. Promos oficiales: el JSON de `cinemex.com/promociones` detecta campañas; las bases con precio requieren probar `rest/v2.2/landings/{slug}` con los headers del scraper.
4. Comparar delivery contra delivery (Cinépolis en Uber Eats/Rappi), nunca delivery contra tablero de sala.
5. Frecuencia diaria o semanal basta: los precios no cambiaron entre dic-2025 (PriceListo) y hoy.

## Lo que no se encontró

Ningún precio del tablero de sala de Cinemex por cine (tamaños chico/mediano/grande, refresco de máquina, ICEE,
dulces sueltos); Cinemex no publica listas de precios en redes (van en imagen); PROFECO no cubre dulcería de cines;
Reddit, Google Maps, TripAdvisor y Foursquare sin fotos de tableros indexadas; no existen datos abiertos ni APIs de
terceros con menús de cines en México; `getStoreV1` no se verificó para Cinépolis.
