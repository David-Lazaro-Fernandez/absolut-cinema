// Cliente de la API de "¿A dónde ir?" (`api/main.py`). NEXT_PUBLIC_API_URL fija la dirección al construir el sitio.
// Cada consulta espera `wait` ms después del último cambio (WAIT_MS por omisión) y cancela la anterior. Lo que ya está
// en caché responde sin esperar. La caché dura CACHE_MS porque la API
// quita cada minuto las funciones que ya empezaron.

import { useEffect, useState } from 'react';
import type { Query } from '@/lib/recommend';

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const WAIT_MS = 250;
const CACHE_MS = 60_000;
const CACHE_MAX = 100;

const cache = new Map<string, { at: number; data: unknown }>();

/** Texto para el visitante cuando la API falla. */
function problem(status: number, detail: unknown) {
  if (status === 429) return 'Hiciste muchas búsquedas seguidas. Espera un minuto y vuelve a intentar.';
  if (status === 422 && typeof detail === 'string') return detail;
  return 'La cartelera no está disponible en este momento.';
}

function cached(url: string) {
  const hit = cache.get(url);
  return hit && Date.now() - hit.at < CACHE_MS ? hit.data : undefined;
}

async function load(url: string, signal: AbortSignal) {
  const hit = cached(url);
  if (hit !== undefined) return hit;
  const res = await fetch(url, { signal }).catch((e) => {
    throw signal.aborted ? e : new Error(problem(0, null));
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(problem(res.status, body?.detail));
  cache.delete(url);
  cache.set(url, { at: Date.now(), data: body });
  if (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value!);
  return body;
}

// Los valores por omisión de `api/main.py`. Un parámetro igual a su valor por omisión no va en la URL.
const API_DEFAULTS: Record<string, string> = {
  adultos: '2',
  ninos: '0',
  mayores: '0',
  dulceria: 'none',
  radio: '5',
  desde: '0',
  hasta: '24',
  orden: 'distance',
};

export function searchParams(q: Query) {
  const all: Record<string, string | number | null> = {
    lat: q.lat,
    lng: q.lng,
    fecha: q.date,
    adultos: q.adults,
    ninos: q.children,
    mayores: q.seniors,
    dulceria: q.snacks,
    combo: q.combo,
    presupuesto: q.budget,
    radio: q.radiusKm,
    desde: q.hours[0],
    hasta: q.hours[1],
    pelicula: q.title,
    formato: q.format,
    orden: q.sort,
    sitio: q.site ? `${q.site.lat},${q.site.lng}` : null,
  };
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(all)) {
    if (value !== null && String(value) !== API_DEFAULTS[key]) p.set(key, String(value));
  }
  return p;
}

/** Consulta `path` con `params`. Con `params` null, no consulta y limpia el estado. Un cambio de `refresh` consulta
 *  otra vez. Mientras carga, `data` conserva la respuesta anterior. `wait` 0 para un clic: no hay nada que agrupar. */
export function useApi<T>(path: string, params: URLSearchParams | null, refresh: unknown = null, wait = WAIT_MS) {
  const query = params ? String(params) : '';
  const url = params ? `${API_URL}${path}${query ? `?${query}` : ''}` : null;
  const [state, setState] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: '', loading: false });
  useEffect(() => {
    if (!url) {
      setState({ data: null, error: '', loading: false });
      return;
    }
    const hit = cached(url);
    if (hit !== undefined) {
      setState({ data: hit as T, error: '', loading: false });
      return;
    }
    setState((s) => ({ ...s, loading: true }));
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      load(url, ctrl.signal)
        .then((data) => setState({ data: data as T, error: '', loading: false }))
        .catch((e: Error) => {
          if (!ctrl.signal.aborted) setState((s) => ({ ...s, error: e.message, loading: false }));
        });
    }, wait);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [url, refresh, wait]);
  return state;
}
