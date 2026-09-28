// Búsqueda local para las sugerencias de /a-donde-ir/. Busca en el índice de `scripts/export_places.py` y en los cines
// del catálogo, sin red. El geocodificador en línea completa las direcciones con número.

import { distanceKm } from '@/lib/recommend';

export type PlacesFile = { version: number; generated_at: string; kinds: string[]; places: [string, number, number, number][] };

export type Place = {
  name: string;
  context: string; // el texto gris de la sugerencia: "Colonia", "Metro", "Cine · Cinépolis"
  rank: number; // prioridad del tipo; el menor va primero
  lat: number;
  lng: number;
  plain: string;
  words: string[];
};

/** Minúsculas, sin acentos ni signos: "Álvaro Obregón" → "alvaro obregon". */
export function plain(text: string) {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9ñ\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Así "roma" también empieza igual que "Colonia Roma Norte".
const LEADING = /^(colonia|col|barrio|fraccionamiento|unidad habitacional|pueblo|estacion) /;

export function makePlace(name: string, context: string, rank: number, lat: number, lng: number): Place {
  const p = plain(name);
  // Sin texto gris si el nombre ya dice el tipo ("Colonia Roma Norte").
  const shown = p.startsWith(`${plain(context)} `) ? '' : context;
  return { name, context: shown, rank, lat, lng, plain: p.replace(LEADING, ''), words: p.split(' ') };
}

/** El índice de lugares, con los cines del catálogo en el rango que se indique. */
export function buildIndex(file: PlacesFile | null, cinemas: { name: string; chain: string; lat: number; lng: number }[], cinemaRank = 3) {
  const out: Place[] = [];
  for (const [name, kind, lat, lng] of file?.places ?? []) out.push(makePlace(name, file!.kinds[kind], kind < cinemaRank ? kind : kind + 1, lat, lng));
  for (const c of cinemas) out.push(makePlace(c.name, `Cine · ${c.chain}`, cinemaRank, c.lat, c.lng));
  return out;
}

/** Los `limit` lugares que coinciden con `query`. Cada palabra de `query` debe iniciar una palabra del nombre.
 *  Orden: los que empiezan igual, el tipo, la distancia a `near` y el nombre más corto. */
export function searchPlaces(index: Place[], query: string, near: { lat: number; lng: number }, limit: number) {
  const q = plain(query);
  if (!q) return [];
  const tokens = q.split(' ');
  const hits: { place: Place; score: number; km: number }[] = [];
  for (const place of index) {
    if (!tokens.every((t) => place.words.some((w) => w.startsWith(t)))) continue;
    hits.push({ place, score: place.plain.startsWith(q) ? 0 : 1, km: distanceKm(near.lat, near.lng, place.lat, place.lng) });
  }
  hits.sort((a, b) => a.score - b.score || a.place.rank - b.place.rank || a.km - b.km || a.place.name.length - b.place.name.length);
  const seen = new Set<string>();
  const out: Place[] = [];
  for (const { place } of hits) {
    const key = `${place.plain}|${place.context}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(place);
    if (out.length >= limit) break;
  }
  return out;
}
