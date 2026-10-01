// Tipos y etiquetas de "¿A dónde ir?". La API calcula (`api/main.py` sobre `analytics/recommender.py`). Este módulo
// describe sus respuestas, con los mismos nombres de campo.

export type Snacks = 'none' | 'best' | 'popcorn' | 'combo_1' | 'combo_2' | 'combo_3' | 'combo_4';

/** Un combo de `analytics/snack_combos.csv`: cuántas personas cubre y a quién ("all", "children" o "adults"). */
export type Combo = { name: string; min: number; max: number; for: 'all' | 'children' | 'adults' };

/** Una línea del desglose de dulcería de una función. */
export type SnackItem = { name: string; units: number; price: number };
export type Sort = 'distance' | 'price' | 'time';

/** Una plaza: clave, etiqueta, centro de sus cines y caja [oeste, sur, este, norte]. */
export type Plaza = { plaza: string; label: string; lat: number; lng: number; bbox: [number, number, number, number] };

/** `GET /v1/a-donde-ir/opciones`. */
export type Options = {
  plazas: Plaza[];
  dates: { date: string }[];
  formats: string[];
  cinemas: { chain: string; chain_label: string; cinema_name: string; lat: number; lng: number }[];
  snacks: Snacks[];
  combos: Combo[];
  captured_at: string | null;
};

export type Row = {
  chain: string;
  show_id: string;
  cinema_name: string;
  lat: number;
  lng: number;
  title: string;
  date: string;
  datetime_local: string;
  language: string;
  format_bucket: string;
  distance_km: number;
  buy_url: string | null;
  box_office_only: boolean;
  tickets_total: number | null;
  snacks_total: number | null;
  snacks_items: SnackItem[] | null;
  snack_reference: number | null;
  total: number | null;
  promo: Promo | null;
};

/** La promoción del día de la función, para `people` personas (1 o 2). `price_max` solo si la cadena publica dos precios sin decir
 *  cuál tiene el cine. `applied`: ya va en boletos, dulcería y `total`. `program` y `program_about`: el programa que
 *  pide (Loop, Club Cinépolis) y qué es; null si no pide cuenta. */
export type Promo = {
  name: string;
  kind: 'combo' | '2x1';
  includes: string;
  program: string | null;
  program_about: string | null;
  condition: string;
  price: number;
  price_max: number | null;
  people: number;
  applied: boolean;
};

/** Un punto del mapa: un edificio con funciones que caben (el complejo y su sala Platino o VIP juntos). */
export type Site = {
  lat: number;
  lng: number;
  distance_km: number;
  shows: number;
  cinemas: { chain: string; chain_label: string; cinema_name: string }[];
};

/** `GET /v1/a-donde-ir/funciones`. Las listas traen solo las primeras filas. `summary` cuenta todas. */
export type Search = {
  summary: {
    shows: number;
    cinemas: number;
    snacks_unpriced: number;
    unpriced: number;
    nearest: Row | null;
    cheapest: Row | null;
  };
  complete: Row[];
  snacks_unpriced: Row[];
  unpriced: Row[];
  sites: Site[];
  titles: { title_norm: string; title: string }[];
};

export type Query = {
  lat: number;
  lng: number;
  date: string;
  adults: number;
  children: number;
  seniors: number;
  snacks: Snacks;
  combo: string | null;
  budget: number | null;
  radiusKm: number;
  hours: [number, number];
  title: string | null;
  format: string | null;
  sort: Sort;
  site?: { lat: number; lng: number };
};

// Etiquetas de `analytics/labels.py` (FORMAT_LABEL, LANGUAGE_LABEL, SNACK_LABEL, RECOMMEND_SORT).
export const FORMAT_LABEL: Record<string, string> = {
  premium: 'Premium / VIP',
  large: 'Gran formato',
  '3d4d': '3D o 4D',
  traditional: 'Tradicional',
};
export const LANGUAGE_LABEL: Record<string, string> = {
  spanish: 'Español',
  subtitled: 'Subtitulada',
  original: 'Español',
  other: 'Versión original',
};
export const SNACK_LABEL: Record<Snacks, string> = {
  none: 'Sin dulcería',
  best: 'Lo más barato para el grupo',
  popcorn: 'Palomitas y refresco por persona',
  combo_1: 'Un combo por persona',
  combo_2: 'Un combo cada dos',
  combo_3: 'Un combo cada tres',
  combo_4: 'Un combo cada cuatro',
};
export const SORT_LABEL: Record<Sort, string> = { distance: 'Más cerca', price: 'Más barato', time: 'Más pronto' };

const EARTH_KM = 6371;

export function distanceKm(lat1: number, lng1: number, lat2: number, lng2: number) {
  const rad = (d: number) => (d * Math.PI) / 180;
  const a =
    Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.sqrt(a));
}

/** Índice de la plaza cuyo centro queda más cerca del punto. */
export function nearestPlaza(plazas: Plaza[], lat: number, lng: number) {
  let best = 0;
  plazas.forEach((p, i) => {
    if (distanceKm(lat, lng, p.lat, p.lng) < distanceKm(lat, lng, plazas[best].lat, plazas[best].lng)) best = i;
  });
  return best;
}

/** Hora local de inicio en minutos desde medianoche ("2026-09-29T11:45:00" → 705). */
export function startMinutes(row: Row) {
  return Number(row.datetime_local.slice(11, 13)) * 60 + Number(row.datetime_local.slice(14, 16));
}

/** Fecha y minutos del día en la hora del centro. Las tres plazas usan esa hora. */
export function nowIn(timeZone = 'America/Mexico_City') {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minutes: Number(parts.hour) * 60 + Number(parts.minute) };
}

// Filtros y orden de la lista de resultados. Corren en el navegador sobre las filas cargadas. No cambian el mapa.

/** Franjas de la hora de inicio, en horas. La hora final no entra. */
export const SLOT_HOURS: Record<string, [number, number]> = {
  morning: [0, 12],
  afternoon: [12, 18],
  night: [18, 24],
};
export const SLOT_LABEL: Record<string, string> = {
  morning: 'Antes de las 12 P.M.',
  afternoon: 'De 12 a 6 P.M.',
  night: 'Después de las 6 P.M.',
};

export type RowFilter = {
  chain: string | null;
  title: string;
  maxPrice: number | null;
  slot: string | null;
  promo: boolean;
};
export const NO_FILTER: RowFilter = { chain: null, title: '', maxPrice: null, slot: null, promo: false };

export type RowSort = 'chain' | 'title' | 'price' | 'time' | 'distance';
/** Opciones del orden de la lista. Un `-` al inicio ordena de mayor a menor. */
export const ROW_SORT_LABEL: Record<string, string> = {
  distance: 'Más cerca',
  '-distance': 'Más lejos',
  price: 'Más barato',
  '-price': 'Más caro',
  time: 'Más pronto',
  '-time': 'Más tarde',
  title: 'Película A–Z',
  '-title': 'Película Z–A',
  chain: 'Cadena A–Z',
  '-chain': 'Cadena Z–A',
};

const fold = (text: string) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

export const rowPrice = (r: Row) => r.total ?? r.tickets_total;

/** Con tope de precio, una fila sin precio no pasa. */
export function filterRows(rows: Row[], f: RowFilter) {
  const title = fold(f.title);
  const slot = f.slot ? SLOT_HOURS[f.slot] : null;
  return rows.filter((r) => {
    const price = rowPrice(r);
    const hour = startMinutes(r) / 60;
    return (
      (!f.chain || r.chain === f.chain) &&
      (!title || fold(r.title).includes(title)) &&
      (f.maxPrice === null || (price !== null && price <= f.maxPrice)) &&
      (!slot || (hour >= slot[0] && hour < slot[1])) &&
      (!f.promo || r.promo !== null)
    );
  });
}

const SORT_VALUE: Record<RowSort, (r: Row) => string | number | null> = {
  chain: (r) => r.chain,
  title: (r) => fold(r.title),
  price: rowPrice,
  time: (r) => r.datetime_local,
  distance: (r) => r.distance_km,
};

/** Ordena una copia de las filas con una clave de ROW_SORT_LABEL. Sin clave, devuelve las mismas filas.
 *  Las filas sin valor van al final. Un empate conserva el orden de entrada. */
export function sortRows(rows: Row[], option: string | null) {
  if (!option) return rows;
  const desc = option.startsWith('-');
  const value = SORT_VALUE[option.replace('-', '') as RowSort];
  return [...rows].sort((a, b) => {
    const va = value(a);
    const vb = value(b);
    if (va === null || vb === null) return va === vb ? 0 : va === null ? 1 : -1;
    const order = typeof va === 'number' ? va - (vb as number) : String(va).localeCompare(String(vb), 'es');
    return desc ? -order : order;
  });
}
