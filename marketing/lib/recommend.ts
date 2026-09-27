// Recomendador de funciones que corre en el navegador sobre el catálogo que exporta
// `scripts/export_recommender.py` (formato versión 2, documentado ahí). Los precios ya vienen calculados por
// `analytics/recommender.py`: aquí solo se buscan por cine, formato y tipo de día, se suman para el grupo y se
// filtra y ordena. Es neutral entre cadenas: ninguna gana un empate por ser quien es (design.md §3).

/** Una plaza del catálogo: clave, etiqueta, centro de sus cines y caja [oeste, sur, este, norte]. */
export type Area = [string, string, number, number, [number, number, number, number]];

export type Catalog = {
  version: number;
  generated_at: string;
  plazas: Area[];
  dates: [string, string][];
  chains: string[];
  formats: string[];
  languages: string[];
  titles: string[];
  packages: Record<string, [string, number][]>;
  cinemas: [number, string, number, number, Record<string, number>][];
  prices: Record<string, [number, number, number, string]>;
  shows: [number, number, number, number, number, number[]][];
};

export type Snacks = 'none' | 'popcorn' | 'combo';
export type Sort = 'distance' | 'price' | 'time';

export type Query = {
  lat: number;
  lng: number;
  adults: number;
  children: number;
  seniors: number;
  snacks: Snacks;
  budget: number | null;
  date: string;
  hours: [number, number];
  radiusKm: number;
  title: number | null;
  format: number | null;
  sort: Sort;
  now: { date: string; minutes: number };
};

export type Row = {
  cinema: number;
  cinemaName: string;
  chain: string;
  lat: number;
  lng: number;
  title: string;
  date: string;
  minutes: number;
  format: string;
  language: string;
  distanceKm: number;
  tickets: number | null;
  snacks: number | null;
  total: number | null;
  snackReference: number | null;
  sampled: string | null;
};

export type Result = {
  complete: Row[];
  snacksUnpriced: Row[];
  unpriced: Row[];
  /** Todas las funciones con precio de boletos que caben, sin tope por cine: la ficha de un cine en el mapa. */
  fitting: Row[];
  /** Cuántas funciones hay en cada lista antes del tope por cine y del límite (las listas traen solo las primeras). */
  counts: { complete: number; snacksUnpriced: number; unpriced: number };
  cinemas: number;
  cheapest: Row | null;
  nearest: Row | null;
  saving: number | null;
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
  popcorn: 'Palomitas y refresco por persona',
  combo: 'Un Combo Clásico cada dos',
};
export const SORT_LABEL: Record<Sort, string> = { distance: 'Más cerca', price: 'Más barato', time: 'Más pronto' };

const EARTH_KM = 6371;
const PER_CINEMA = 3;
const LIMIT = 40;

export function distanceKm(lat1: number, lng1: number, lat2: number, lng2: number) {
  const rad = (d: number) => (d * Math.PI) / 180;
  const a =
    Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.sqrt(a));
}

/** Índice de la plaza cuyo centro queda más cerca del punto. */
export function nearestPlaza(plazas: Area[], lat: number, lng: number) {
  let best = 0;
  plazas.forEach((a, i) => {
    if (distanceKm(lat, lng, a[2], a[3]) < distanceKm(lat, lng, plazas[best][2], plazas[best][3])) best = i;
  });
  return best;
}

/** Costo de un paquete de dulcería para `people` en un cine; null si su menú no tiene alguno de los productos. */
export function packageCost(menu: Record<string, number>, items: [string, number][], people: number) {
  let total = 0;
  for (const [product, covers] of items) {
    if (!(product in menu)) return null;
    total += menu[product] * Math.ceil(people / covers);
  }
  return total;
}

/** Fecha y minutos del día en la zona horaria de las plazas (CDMX, Guadalajara y Monterrey van a la hora del centro). */
export function nowIn(timeZone = 'America/Mexico_City') {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minutes: Number(parts.hour) * 60 + Number(parts.minute) };
}

function cost(r: Row) {
  return r.total ?? r.tickets ?? Infinity;
}

const SORTS: Record<Sort, (a: Row, b: Row) => number> = {
  distance: (a, b) => a.distanceKm - b.distanceKm || cost(a) - cost(b) || a.minutes - b.minutes,
  price: (a, b) => cost(a) - cost(b) || a.distanceKm - b.distanceKm || a.minutes - b.minutes,
  time: (a, b) => a.minutes - b.minutes || a.distanceKm - b.distanceKm || cost(a) - cost(b),
};

function capped(rows: Row[], sort: Sort) {
  const taken = new Map<number, number>();
  const out: Row[] = [];
  for (const r of [...rows].sort(SORTS[sort])) {
    const n = taken.get(r.cinema) ?? 0;
    if (n >= PER_CINEMA) continue;
    taken.set(r.cinema, n + 1);
    out.push(r);
    if (out.length >= LIMIT) break;
  }
  return out;
}

export function recommend(catalog: Catalog, q: Query): Result {
  const people = q.adults + q.children + q.seniors;
  const dayType = Object.fromEntries(catalog.dates);
  const dateIx = catalog.dates.findIndex(([d]) => d === q.date);
  const items = catalog.packages[q.snacks] ?? [];
  const reference = catalog.packages.popcorn ?? [];
  const near = new Map<number, number>();
  catalog.cinemas.forEach(([, , lat, lng], i) => {
    const km = distanceKm(q.lat, q.lng, lat, lng);
    if (km <= q.radiusKm) near.set(i, km);
  });
  const rows: Row[] = [];
  for (const [cinema, date, title, format, language, times] of catalog.shows) {
    if (date !== dateIx || !near.has(cinema)) continue;
    if (q.title !== null && title !== q.title) continue;
    if (q.format !== null && format !== q.format) continue;
    const [chain, name, lat, lng, menu] = catalog.cinemas[cinema];
    const price = catalog.prices[`${cinema}|${format}|${dayType[q.date]}`];
    const tickets = price ? q.adults * price[0] + q.children * price[1] + q.seniors * price[2] : null;
    const snacks = q.snacks === 'none' ? 0 : packageCost(menu, items, people);
    for (const minutes of times) {
      if (q.date === q.now.date && minutes < q.now.minutes) continue;
      if (minutes < q.hours[0] * 60 || minutes >= q.hours[1] * 60) continue;
      rows.push({
        cinema,
        cinemaName: name,
        chain: catalog.chains[chain],
        lat,
        lng,
        title: catalog.titles[title],
        date: q.date,
        minutes,
        format: catalog.formats[format],
        language: catalog.languages[language],
        distanceKm: near.get(cinema)!,
        tickets,
        snacks,
        total: tickets !== null && snacks !== null ? tickets + snacks : null,
        snackReference: packageCost(menu, reference, 1),
        sampled: price ? price[3] : null,
      });
    }
  }
  const fits = (r: Row) => q.budget === null || cost(r) <= q.budget;
  const complete = rows.filter((r) => r.total !== null && fits(r));
  const partial = rows.filter((r) => r.tickets !== null && r.total === null && fits(r));
  const byPrice = [...complete].sort(SORTS.price);
  const unpriced = rows.filter((r) => r.tickets === null);
  return {
    complete: capped(complete, q.sort),
    snacksUnpriced: capped(partial, q.sort),
    unpriced: capped(unpriced, 'distance'),
    counts: { complete: complete.length, snacksUnpriced: partial.length, unpriced: unpriced.length },
    fitting: [...complete, ...partial].sort((a, b) => a.minutes - b.minutes),
    cinemas: new Set(complete.map((r) => r.cinema)).size,
    cheapest: byPrice[0] ?? null,
    nearest: [...complete].sort(SORTS.distance)[0] ?? null,
    saving: byPrice.length ? byPrice[byPrice.length - 1].total! - byPrice[0].total! : null,
  };
}

/** Películas con funciones cerca en ese día: [índice, título, funciones], de más a menos funciones. */
export function titlesNear(catalog: Catalog, lat: number, lng: number, radiusKm: number, date: string) {
  const dateIx = catalog.dates.findIndex(([d]) => d === date);
  const count = new Map<number, number>();
  for (const [cinema, d, title, , , times] of catalog.shows) {
    if (d !== dateIx) continue;
    const [, , clat, clng] = catalog.cinemas[cinema];
    if (distanceKm(lat, lng, clat, clng) > radiusKm) continue;
    count.set(title, (count.get(title) ?? 0) + times.length);
  }
  return [...count.entries()]
    .sort((a, b) => b[1] - a[1] || catalog.titles[a[0]].localeCompare(catalog.titles[b[0]]))
    .map(([i, n]) => [i, catalog.titles[i], n] as const);
}
