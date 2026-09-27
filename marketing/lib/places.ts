// Búsqueda local de lugares para las sugerencias instantáneas de /a-donde-ir/: el índice de CDMX que exporta
// `scripts/export_places.py` (colonias, alcaldías, estaciones, plazas, universidades de OpenStreetMap) más los cines
// del catálogo. Sin red: responde al teclear. Las direcciones con número las completa el geocodificador en línea.

import { distanceKm } from '@/lib/recommend';

export type PlacesFile = { version: number; generated_at: string; kinds: string[]; places: [string, number, number, number][] };

export type Place = {
  name: string;
  context: string; // qué es ("Colonia", "Metro", "Cine · Cinépolis"): la línea gris de la sugerencia
  rank: number; // prioridad del tipo: menor va antes a igual coincidencia
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

// "Colonia Roma Norte" también debe empezar con "roma": el prefijo del tipo no cuenta para "empieza igual".
const LEADING = /^(colonia|col|barrio|fraccionamiento|unidad habitacional|pueblo|estacion) /;

export function makePlace(name: string, context: string, rank: number, lat: number, lng: number): Place {
  const p = plain(name);
  // "Colonia Roma Norte" no necesita el gris "Colonia": el nombre ya dice qué es.
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

/** Los `limit` lugares que coinciden con `query`: toda palabra escrita debe iniciar una palabra del nombre. Primero
 *  los que empiezan igual que lo escrito, luego por tipo, cercanía a `near` y nombre más corto. */
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
