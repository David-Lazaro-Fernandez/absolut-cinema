'use client';

// "¿A dónde ir?": funciones cerca del visitante que caben en el presupuesto de su grupo. La página descarga una vez
// el catálogo de `scripts/export_recommender.py` y lo filtra con `lib/recommend.ts`, sin servidor.

import dynamic from 'next/dynamic';
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { preconnect } from 'react-dom';
import { type PlacesFile, buildIndex, makePlace, plain, searchPlaces } from '@/lib/places';
import { Calendar, Close, Locate, People, Pin, Popcorn, Send, Sliders, Wallet } from '@/components/rec-icons';
import {
  type Catalog,
  type Row,
  type Snacks,
  type Sort,
  FORMAT_LABEL,
  LANGUAGE_LABEL,
  SNACK_LABEL,
  SORT_LABEL,
  nearestPlaza,
  nowIn,
  recommend,
  titlesNear,
} from '@/lib/recommend';

const RecommenderMap = dynamic(() => import('@/components/recommender-map'), { ssr: false });

const CATALOG_URL = '/data/a-donde-ir.json';
const PLACES_URL = '/data/lugares.json'; // de scripts/export_places.py; si falta, solo sugiere el geocodificador
// Photon (komoot, datos de OpenStreetMap) permite sugerir mientras se escribe y no pide clave. Nominatim lo prohíbe.
// La instancia pública es de uso justo: con tráfico real, usar una instancia propia.
const GEOCODER = 'https://photon.komoot.io/api/';
const DEFAULT_CENTER = { lat: 19.4326, lng: -99.1332 }; // CDMX, hasta que carga el catálogo
const LOCAL_MIN_CHARS = 2;
const ONLINE_MIN_CHARS = 3;
const SUGGEST_WAIT_MS = 250;
const SUGGEST_LIMIT = 3;
const CACHE_KEY = 'matine-geocode-v2';
const CACHE_MAX = 60;

type Suggestion = { lat: number; lng: number; name: string; context: string };

type PhotonFeature = {
  geometry: { coordinates: [number, number] };
  properties: Record<string, string | undefined>;
};

function toSuggestion(f: PhotonFeature): Suggestion {
  const p = f.properties;
  const street = [p.street, p.housenumber].filter(Boolean).join(' ');
  const context = [street, p.district ?? p.locality, p.city ?? p.county, p.state]
    .filter((v, i, all) => v && v !== p.name && all.indexOf(v) === i)
    .join(', ');
  return { lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0], name: p.name ?? street, context };
}

// Respuestas del geocodificador por plaza y texto ("gdl|centro"). Las últimas CACHE_MAX quedan en localStorage.
// Mientras llega una respuesta, la página filtra la del texto guardado más largo que empieza igual.
const remoteCache = new Map<string, Suggestion[]>();

function loadCache() {
  try {
    for (const [k, v] of JSON.parse(localStorage.getItem(CACHE_KEY) ?? '[]') as [string, Suggestion[]][]) remoteCache.set(k, v);
  } catch {
    // Sin localStorage (modo privado o bloqueado), la caché queda solo en memoria.
  }
}

function saveCache() {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify([...remoteCache.entries()].slice(-CACHE_MAX)));
  } catch {
  }
}

function cachedNear(scope: string, query: string, near: { lat: number; lng: number }) {
  const q = `${scope}|${plain(query)}`;
  let best = '';
  for (const k of remoteCache.keys()) if (q.startsWith(k) && k.length > best.length) best = k;
  if (!best) return [];
  const pool = remoteCache.get(best)!.map((s) => makePlace(s.name, s.context, 0, s.lat, s.lng));
  return searchPlaces(pool, query, near, SUGGEST_LIMIT).map((p) => ({ lat: p.lat, lng: p.lng, name: p.name, context: p.context }));
}

/** Une las sugerencias sin repetir nombres. Las locales van primero, salvo si el texto tiene un número (una calle). */
function merge(query: string, local: Suggestion[], remote: Suggestion[]) {
  const ordered = /\d/.test(query) ? [...remote, ...local] : [...local, ...remote];
  const seen = new Set<string>();
  const out: Suggestion[] = [];
  for (const s of ordered) {
    const key = plain(s.name);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out.slice(0, SUGGEST_LIMIT);
}

async function geocode(query: string, near: { lat: number; lng: number }, bbox: string, limit: number, signal?: AbortSignal) {
  // Photon no acepta lang=es: con él no devuelve nada. lang=default da los nombres locales.
  const params = new URLSearchParams({ q: query, limit: String(limit), lang: 'default', lat: String(near.lat), lon: String(near.lng) });
  if (bbox) params.set('bbox', bbox);
  const res = await fetch(`${GEOCODER}?${params}`, { signal });
  if (!res.ok) throw new Error(String(res.status));
  const data: { features: PhotonFeature[] } = await res.json();
  return data.features.map(toSuggestion).filter((s) => s.name);
}
const HOURS: Record<string, [number, number]> = {
  'Todo el día': [0, 24],
  'Después de las 6 PM': [18, 24],
  'Matiné, antes de las 12 PM': [0, 12],
};
const RADII = [2, 5, 10, 15];
const MAP_OVERLAP = 150; // px del mapa que tapa el dock con punto de partida

type Point = { lat: number; lng: number; label: string };

const siteKey = (p: { lat: number; lng: number }) => `${p.lat},${p.lng}`;

const money = (v: number) =>
  new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(v);
const km = (v: number) => `${v.toFixed(1)} km`;

function time12(minutes: number) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'A.M.' : 'P.M.'}`;
}

function dayLabel(iso: string, today: string) {
  const text = new Intl.DateTimeFormat('es-MX', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(
    new Date(`${iso}T12:00:00Z`),
  );
  return iso === today ? `Hoy, ${text}` : text[0].toUpperCase() + text.slice(1);
}

function groupText(adults: number, children: number, seniors: number) {
  const parts = [
    [adults, 'adulto', 'adultos'],
    [children, 'niño', 'niños'],
    [seniors, 'adulto mayor', 'adultos mayores'],
  ]
    .filter(([n]) => (n as number) > 0)
    .map(([n, one, many]) => `${n} ${n === 1 ? one : many}`);
  if (!parts.length) return 'nadie todavía';
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} y ${parts[parts.length - 1]}` : parts[0];
}

function Counter({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div className="rec__counter">
      <span className="rec__label">{label}</span>
      <div className="rec__stepper">
        <button type="button" aria-label={`Menos ${label.toLowerCase()}`} onClick={() => onChange(Math.max(0, value - 1))}>
          −
        </button>
        <output>{value}</output>
        <button type="button" aria-label={`Más ${label.toLowerCase()}`} onClick={() => onChange(Math.min(10, value + 1))}>
          +
        </button>
      </div>
    </div>
  );
}

function BuyLink({ row }: { row: Row }) {
  if (!row.buyUrl) return null;
  return (
    <a className="rec__buy" href={row.buyUrl} target="_blank" rel="noopener noreferrer" aria-label={`Comprar en ${row.chain} (abre su sitio)`}>
      Comprar ↗
    </a>
  );
}

function ShowsTable({ rows, snacks, today, partial }: { rows: Row[]; snacks: Snacks; today: string; partial?: boolean }) {
  return (
    <div className="rec__tablewrap">
      <table className="rec__table">
        <thead>
          <tr>
            <th>Cine</th>
            <th>Película</th>
            <th>Función</th>
            <th>Formato</th>
            <th className="num">Boletos</th>
            {!partial && <th className="num">Dulcería</th>}
            {!partial && <th className="num">Total</th>}
            <th className="num">Distancia</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.cinema}-${r.title}-${r.minutes}-${r.format}`}>
              <td className="rec__c-cinema">
                <strong>{r.cinemaName}</strong>
                <span className="rec__chain">{r.chain}</span>
              </td>
              <td className="rec__c-title">{r.title}</td>
              <td className="num rec__c-time">
                {r.date === today ? time12(r.minutes) : `${dayLabel(r.date, today)}, ${time12(r.minutes)}`}
                <BuyLink row={r} />
              </td>
              <td className="rec__c-format">
                {FORMAT_LABEL[r.format] ?? r.format}
                <span className="rec__chain">{LANGUAGE_LABEL[r.language] ?? r.language}</span>
              </td>
              <td className="num rec__c-tickets" data-label="Boletos">{r.tickets !== null ? money(r.tickets) : '—'}</td>
              {!partial && (
                <td className="num rec__c-snacks" data-label="Dulcería">
                  {snacks !== 'none'
                    ? money(r.snacks!)
                    : r.snackReference !== null
                      ? <span className="rec__ref" title="Palomitas y refresco para una persona, como referencia">ref. {money(r.snackReference)}</span>
                      : <span className="rec__ref">sin precio en sala</span>}
                </td>
              )}
              {!partial && <td className="num rec__total rec__c-total">{money(r.total!)}</td>}
              <td className="num rec__c-dist">{km(r.distanceKm)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type RowId = 'group' | 'snacks' | 'when' | 'budget' | 'more';
type Tab = 'complete' | 'snacksUnpriced' | 'unpriced';
const PAGE = 10; // funciones por página en la pantalla de resultados

function MenuRow({
  id,
  open,
  onToggle,
  icon,
  label,
  value,
  children,
}: {
  id: RowId;
  open: RowId | null;
  onToggle: (id: RowId) => void;
  icon: ReactNode;
  label: string;
  value: string;
  children: ReactNode;
}) {
  const isOpen = open === id;
  return (
    <div className={`rec-menu__row ${isOpen ? 'is-open' : ''}`}>
      <button type="button" className="rec-menu__head" aria-expanded={isOpen} onClick={() => onToggle(id)}>
        <span className="rec-menu__icon">{icon}</span>
        <span className="rec-menu__label">{label}</span>
        <span className="rec-menu__value">{value}</span>
        {isOpen && (
          <span className="rec-menu__close" aria-hidden="true">
            <Close />
          </span>
        )}
      </button>
      {isOpen && <div className="rec-menu__body">{children}</div>}
    </div>
  );
}

export function Recommender() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [failed, setFailed] = useState(false);
  const [start, setStart] = useState<Point | null>(null);
  const [address, setAddress] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState(0);
  const [seniors, setSeniors] = useState(0);
  const [budget, setBudget] = useState('');
  const [snacks, setSnacks] = useState<Snacks>('none');
  const [date, setDate] = useState('');
  const [hours, setHours] = useState('Todo el día');
  const [radiusKm, setRadiusKm] = useState(5);
  const [title, setTitle] = useState<number | null>(null);
  const [format, setFormat] = useState<number | null>(null);
  const [sort, setSort] = useState<Sort>('distance');
  const [open, setOpen] = useState<RowId | null>(null);
  const [menu, setMenu] = useState(false);
  const [view, setView] = useState<'search' | 'results'>('search');
  const [selected, setSelected] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [placesFile, setPlacesFile] = useState<PlacesFile | null>(null);
  const [active, setActive] = useState(-1);
  const [typing, setTyping] = useState(false);
  const [tab, setTab] = useState<Tab>('complete');
  const [shown, setShown] = useState(PAGE);
  const [plaza, setPlaza] = useState(0); // índice en catalog.plazas
  const menuBox = useRef<HTMLDivElement>(null);
  // Cada minuto: con la página abierta, una función que ya empezó sale de los resultados.
  const [now, setNow] = useState(() => nowIn());
  useEffect(() => {
    const timer = setInterval(() => setNow(nowIn()), 60_000);
    return () => clearInterval(timer);
  }, []);
  const toggle = (id: RowId) => setOpen((o) => (o === id ? null : id));
  const area = catalog?.plazas[plaza];
  const scope = area?.[0] ?? '';
  const bbox = area ? area[4].join(',') : '';
  const center = useMemo(() => (area ? { lat: area[2], lng: area[3] } : DEFAULT_CENTER), [area]);

  // Con punto de partida, la plaza es la más cercana a él.
  useEffect(() => {
    if (catalog && start) setPlaza(nearestPlaza(catalog.plazas, start.lat, start.lng));
  }, [catalog, start]);

  useEffect(() => {
    if (!menu) return;
    const outside = (e: MouseEvent) => {
      if (menuBox.current && !menuBox.current.contains(e.target as Node)) setMenu(false);
    };
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false);
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [menu]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
    setShown(PAGE);
  }, [view, tab]);

  // Un enlace con ?lat=19.35&lng=-99.16 abre la página con ese punto de partida.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const lat = Number(q.get('lat'));
    const lng = Number(q.get('lng'));
    if (q.has('lat') && q.has('lng') && Number.isFinite(lat) && Number.isFinite(lng))
      setStart({ lat, lng, label: 'el punto del enlace' });
  }, []);

  useEffect(() => {
    fetch(CATALOG_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((c: Catalog) => {
        setCatalog(c);
        setDate(c.dates.some(([d]) => d === now.date) ? now.date : c.dates[0]?.[0] ?? '');
      })
      .catch(() => setFailed(true));
  }, [now.date]);

  // La conexión con el geocodificador abre antes de la primera búsqueda. En una red lenta, el saludo TLS es buena
  // parte de la espera.
  useEffect(() => {
    preconnect(new URL(GEOCODER).origin);
    loadCache();
    fetch(PLACES_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then((f: PlacesFile | null) => setPlacesFile(f))
      .catch(() => undefined);
  }, []);

  const placeIndex = useMemo(
    () =>
      buildIndex(
        placesFile,
        (catalog?.cinemas ?? []).map(([chain, name, lat, lng]) => ({ name, chain: catalog!.chains[chain], lat, lng })),
      ),
    [placesFile, catalog],
  );

  // Las sugerencias locales salen al instante. El geocodificador responde solo si las locales no alcanzan o si el
  // texto tiene un número, después de una pausa. Una respuesta vieja se descarta.
  useEffect(() => {
    const q = address.trim();
    if (!typing || q.length < LOCAL_MIN_CHARS) {
      setSuggestions([]);
      return;
    }
    const near = start ?? center;
    const local = searchPlaces(placeIndex, q, near, SUGGEST_LIMIT).map(({ lat, lng, name, context }) => ({ lat, lng, name, context }));
    const key = `${scope}|${plain(q)}`;
    const show = (remote: Suggestion[]) => {
      const merged = merge(q, local, remote);
      setSuggestions(merged);
      setActive(merged.length ? 0 : -1);
    };
    show(remoteCache.get(key) ?? cachedNear(scope, q, near));
    if (q.length < ONLINE_MIN_CHARS || remoteCache.has(key) || (local.length >= SUGGEST_LIMIT && !/\d/.test(q))) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      geocode(q, near, bbox, SUGGEST_LIMIT, ctrl.signal)
        .then((found) => {
          remoteCache.set(key, found);
          saveCache();
          show(found);
        })
        .catch(() => undefined);
    }, SUGGEST_WAIT_MS);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [address, typing, start, placeIndex, center, scope, bbox]);

  const days = useMemo(() => (catalog ? catalog.dates.map(([d]) => d).filter((d) => d >= now.date) : []), [catalog, now.date]);
  const people = adults + children + seniors;
  const titles = useMemo(
    () => (catalog && start && date ? titlesNear(catalog, start.lat, start.lng, radiusKm, date) : []),
    [catalog, start, radiusKm, date],
  );
  const result = useMemo(() => {
    if (!catalog || !start || !people || !date) return null;
    const limit = Number(budget.replace(/[^\d]/g, ''));
    return recommend(catalog, {
      lat: start.lat,
      lng: start.lng,
      adults,
      children,
      seniors,
      snacks,
      budget: limit > 0 ? limit : null,
      date,
      hours: HOURS[hours],
      radiusKm,
      title,
      format,
      sort,
      now,
    });
  }, [catalog, start, people, adults, children, seniors, snacks, budget, date, hours, radiusKm, title, format, sort, now]);
  // Un punto por edificio: el complejo y su sala Platino o VIP comparten coordenadas, y un punto tapaba al otro.
  const sites = useMemo(() => {
    const byPlace = new Map<string, { id: number; lat: number; lng: number; names: string[]; chains: string[] }>();
    for (const r of result?.fitting ?? []) {
      const site = byPlace.get(siteKey(r)) ?? { id: r.cinema, lat: r.lat, lng: r.lng, names: [], chains: [] };
      if (!site.names.includes(r.cinemaName)) site.names.push(r.cinemaName);
      if (!site.chains.includes(r.chain)) site.chains.push(r.chain);
      byPlace.set(siteKey(r), site);
    }
    return [...byPlace.values()].map((s) => ({ ...s, name: s.names.join(' · '), chain: s.chains.join(' · ') }));
  }, [result]);
  const site = sites.find((s) => s.id === selected) ?? null;
  const siteRows = useMemo(
    () => (result && site ? result.fitting.filter((r) => siteKey(r) === siteKey(site)) : []),
    [result, site],
  );

  function choose(place: Suggestion) {
    setStart({ lat: place.lat, lng: place.lng, label: place.context ? `${place.name}, ${place.context}` : place.name });
    setAddress(place.name);
    setSuggestions([]);
    setTyping(false);
    setSelected(null);
    setNotice('');
  }

  // Enviar sin elegir toma la sugerencia marcada, o busca la primera coincidencia.
  async function search(e: React.SyntheticEvent) {
    e.preventDefault();
    if (suggestions.length) return choose(suggestions[Math.max(active, 0)]);
    if (!address.trim()) return;
    setBusy(true);
    setNotice('');
    try {
      const [first] = await geocode(address.trim(), start ?? center, bbox, 1);
      if (first) choose(first);
      else setNotice('No encontramos esa dirección. Prueba con calle y colonia, o haz doble clic en el mapa.');
    } catch {
      setNotice('El buscador de direcciones no respondió. Haz doble clic en el mapa para marcar tu punto.');
    } finally {
      setBusy(false);
    }
  }

  function keys(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!suggestions.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => (i + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => (i - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Escape') {
      setSuggestions([]);
      setTyping(false);
    }
  }

  function locate() {
    if (!navigator.geolocation) return setNotice('Tu navegador no comparte ubicación. Escribe una dirección o haz doble clic en el mapa.');
    setBusy(true);
    setNotice('');
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setStart({ lat: p.coords.latitude, lng: p.coords.longitude, label: 'Tu ubicación actual' });
        setBusy(false);
      },
      () => {
        setNotice('No pudimos usar tu ubicación. Escribe una dirección o haz doble clic en el mapa.');
        setBusy(false);
      },
    );
  }

  const generated = catalog
    ? new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'long', hour: 'numeric', minute: '2-digit', timeZone: 'America/Mexico_City' }).format(
        new Date(catalog.generated_at),
      )
    : '';
  const budgetValue = Number(budget.replace(/[^\d]/g, ''));
  const lists: Record<Tab, Row[]> = {
    complete: result?.complete ?? [],
    snacksUnpriced: snacks !== 'none' ? result?.snacksUnpriced ?? [] : [],
    unpriced: result?.unpriced ?? [],
  };
  const tabs: [Tab, string][] = [
    ['complete', 'Caben'],
    ['snacksUnpriced', 'Sin precio de dulcería'],
    ['unpriced', 'Sin precio de boletos'],
  ];
  const ready = catalog && start && people;

  if (view === 'results' && ready && result) {
    const rows = lists[tab];
    return (
      <section className="rec-screen">
        <div className="rec-screen__bar">
          <button type="button" className="pill pill--ghost pill--sm" onClick={() => setView('search')}>
            ← Cambiar búsqueda
          </button>
          <span className="rec-screen__plan">
            {groupText(adults, children, seniors)} · {SNACK_LABEL[snacks].toLowerCase()} · {dayLabel(date, now.date).toLowerCase()}
            {budgetValue > 0 ? ` · hasta ${money(budgetValue)}` : ''}
          </span>
        </div>
        <h1 className="rec-screen__title">Funciones para {groupText(adults, children, seniors)}</h1>
        {result.complete.length ? (
          <p className="rec__lead">
            {result.cinemas} {result.cinemas === 1 ? 'cine tiene' : 'cines tienen'} funciones que caben
            {budgetValue > 0 ? ' en tu presupuesto' : ''} a {radiusKm} km o menos de tu punto de partida.
            {result.cheapest && ` La más barata: ${result.cheapest.cinemaName} (${result.cheapest.chain}), ${money(result.cheapest.total!)} en total a ${km(result.cheapest.distanceKm)}.`}
            {result.nearest && ` La más cercana: ${result.nearest.cinemaName}, a ${km(result.nearest.distanceKm)}.`}
          </p>
        ) : (
          <p className="rec__lead">
            Ninguna función con costo completo cabe con esos filtros. Cambia la búsqueda: más distancia, otro horario, otra dulcería o más
            presupuesto.
          </p>
        )}

        <div className="rec-tabs" role="tablist">
          {tabs
            .filter(([t]) => t === 'complete' || lists[t].length > 0)
            .map(([t, label]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} className={`rec-tabs__tab ${tab === t ? 'is-on' : ''}`} onClick={() => setTab(t)}>
                {label} <span>{result.counts[t].toLocaleString('es-MX')}</span>
              </button>
            ))}
        </div>

        {tab === 'snacksUnpriced' && (
          <p className="rec__hint">
            Estos cines no publican el precio de su dulcería en sala: solo sabemos cuánto cuestan los boletos y no los comparamos con los que caben.
          </p>
        )}
        {tab === 'unpriced' && <p className="rec__hint">No hay precio de lista de su cine para ese formato y día; por eso no entran al presupuesto.</p>}

        {rows.length > 0 && (
          <ShowsTable rows={rows.slice(0, shown)} snacks={snacks} today={now.date} partial={tab !== 'complete'} />
        )}
        {rows.length > shown && (
          <button type="button" className="pill pill--ghost rec-screen__more" onClick={() => setShown((n) => n + PAGE)}>
            Ver {Math.min(PAGE, rows.length - shown)} más
          </button>
        )}

        <p className="rec__source">
          Cartelera y precios de lista de Cinemex, Cinépolis y la Cineteca Nacional capturados por Matiné; datos del {generated}. Boletos por
          tipo de persona según el formato y el día de cada función; dulcería del menú en sala (tamaño base), solo donde el cine lo publica;
          sin cargo por servicio. Distancia en línea recta; ninguna cadena gana un empate por ser quien es. Direcciones: Photon (komoot) ©
          OpenStreetMap. Mapa © OpenFreeMap y OpenStreetMap.
        </p>
      </section>
    );
  }

  const located = Boolean(start);
  const menuRows = (
    <div className={`rec-menu ${located ? '' : 'rec-menu--down'}`} role="menu" aria-label="Opciones de la búsqueda">
      <MenuRow id="group" open={open} onToggle={toggle} icon={<People />} label="Quiénes van" value={groupText(adults, children, seniors)}>
        <div className="rec__row">
          <Counter label="Adultos" value={adults} onChange={setAdults} />
          <Counter label="Niños" value={children} onChange={setChildren} />
          <Counter label="Adultos mayores" value={seniors} onChange={setSeniors} />
        </div>
      </MenuRow>
      <MenuRow id="snacks" open={open} onToggle={toggle} icon={<Popcorn />} label="Dulcería" value={SNACK_LABEL[snacks]}>
        <div className="rec__chips" role="radiogroup" aria-label="Dulcería">
          {(Object.keys(SNACK_LABEL) as Snacks[]).map((k) => (
            <button key={k} type="button" role="radio" aria-checked={snacks === k} className={`rec__chip ${snacks === k ? 'is-on' : ''}`} onClick={() => setSnacks(k)}>
              {SNACK_LABEL[k]}
            </button>
          ))}
        </div>
      </MenuRow>
      <MenuRow
        id="when"
        open={open}
        onToggle={toggle}
        icon={<Calendar />}
        label="Cuándo"
        value={date ? `${dayLabel(date, now.date)} · ${hours.toLowerCase()}` : 'Cargando…'}
      >
        <div className="rec__row">
          <label className="rec__field">
            <span className="rec__label">Día</span>
            <select value={date} onChange={(e) => setDate(e.target.value)}>
              {days.map((d) => (
                <option key={d} value={d}>
                  {dayLabel(d, now.date)}
                </option>
              ))}
            </select>
          </label>
          <label className="rec__field">
            <span className="rec__label">Hora de inicio</span>
            <select value={hours} onChange={(e) => setHours(e.target.value)}>
              {Object.keys(HOURS).map((h) => (
                <option key={h}>{h}</option>
              ))}
            </select>
          </label>
        </div>
      </MenuRow>
      <MenuRow
        id="budget"
        open={open}
        onToggle={toggle}
        icon={<Wallet />}
        label="Presupuesto"
        value={budgetValue > 0 ? `${money(budgetValue)} en total` : 'Sin tope'}
      >
        <label className="rec__field">
          <span className="rec__label">Boletos y dulcería para todo el grupo</span>
          <input inputMode="numeric" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="Ej. 600" autoFocus />
        </label>
      </MenuRow>
      <MenuRow id="more" open={open} onToggle={toggle} icon={<Sliders />} label="Más filtros" value={`${radiusKm} km · ${SORT_LABEL[sort].toLowerCase()}`}>
        <div className="rec__row">
          <label className="rec__field">
            <span className="rec__label">Distancia máxima</span>
            <select value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))}>
              {RADII.map((r) => (
                <option key={r} value={r}>
                  {r} km
                </option>
              ))}
            </select>
          </label>
          <label className="rec__field">
            <span className="rec__label">Película</span>
            <select value={title ?? ''} onChange={(e) => setTitle(e.target.value === '' ? null : Number(e.target.value))}>
              <option value="">Cualquier película</option>
              {titles.map(([i, name]) => (
                <option key={i} value={i}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="rec__field">
            <span className="rec__label">Formato</span>
            <select value={format ?? ''} onChange={(e) => setFormat(e.target.value === '' ? null : Number(e.target.value))}>
              <option value="">Cualquier formato</option>
              {(catalog?.formats ?? []).map((f, i) => (
                <option key={f} value={i}>
                  {FORMAT_LABEL[f] ?? f}
                </option>
              ))}
            </select>
          </label>
          <label className="rec__field">
            <span className="rec__label">Ordenar por</span>
            <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              {(Object.keys(SORT_LABEL) as Sort[]).map((k) => (
                <option key={k} value={k}>
                  {SORT_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </MenuRow>
    </div>
  );

  return (
    <section className={`rec-stage ${located ? 'is-located' : ''}`}>
      <div className="rec-stage__map">
        <RecommenderMap
          center={center}
          start={start}
          radiusKm={radiusKm}
          cinemas={sites}
          selected={selected}
          bottomInset={located ? MAP_OVERLAP : 0}
          onPick={(p) => {
            setSelected(null);
            setStart({ ...p, label: 'el punto que marcaste en el mapa' });
          }}
          onCinema={setSelected}
        />
      </div>
      {/* Sin punto de partida, el velo tapa el mapa y bloquea los clics. */}
      <div className="rec-stage__glass" aria-hidden="true" />

      {!located && <h1 className="rec-stage__title">¿A dónde vamos al cine hoy?</h1>}

      {located && site && siteRows.length > 0 && (
        <aside className="rec-card" aria-label={`Funciones en ${site.name}`}>
          <div className="rec-card__head">
            <div>
              <strong>{site.name}</strong>
              <span className="rec__chain">
                {site.chain} · {km(siteRows[0].distanceKm)} · {siteRows.length} {siteRows.length === 1 ? 'función' : 'funciones'}
              </span>
            </div>
            <button type="button" className="rec-card__close" aria-label="Cerrar" onClick={() => setSelected(null)}>
              <Close />
            </button>
          </div>
          <ul className="rec-card__list">
            {siteRows.map((r) => (
              <li key={`${r.cinema}-${r.title}-${r.minutes}-${r.format}`}>
                <span className="rec-card__time">
                  {time12(r.minutes)}
                  <BuyLink row={r} />
                </span>
                <span className="rec-card__title">
                  {r.title}
                  <span className="rec__chain">
                    {site.names.length > 1 && `${r.cinemaName} · `}
                    {FORMAT_LABEL[r.format] ?? r.format} · {LANGUAGE_LABEL[r.language] ?? r.language}
                  </span>
                </span>
                <span className="rec-card__price">
                  {r.total !== null ? money(r.total) : money(r.tickets!)}
                  {r.total === null && <span className="rec__chain">solo boletos</span>}
                </span>
              </li>
            ))}
          </ul>
        </aside>
      )}

      <div className="rec-dock" ref={menuBox}>
        {menu && menuRows}
        {located && (
          <div className="rec-dock__context">
            <span>
              {failed
                ? 'Los datos de cartelera no están disponibles en este momento.'
                : !catalog
                  ? 'Cargando cartelera…'
                  : notice
                    ? notice
                    : !people
                      ? 'Agrega al menos una persona en las opciones.'
                      : `${groupText(adults, children, seniors)} · ${SNACK_LABEL[snacks].toLowerCase()} · toca un cine para ver sus funciones`}
            </span>
            {catalog && people > 0 && result && (
              <button type="button" className="pill pill--primary pill--sm" onClick={() => { setTab('complete'); setView('results'); }}>
                {result.cinemas ? `Ver funciones en ${result.cinemas} ${result.cinemas === 1 ? 'cine' : 'cines'}` : 'Ver resultados'}
              </button>
            )}
          </div>
        )}
        <div className="rec-ask-box">
        {suggestions.length > 0 && (
          <ul className={`rec-suggest ${located ? '' : 'rec-suggest--down'}`} role="listbox" id="rec-suggest" aria-label="Sugerencias de lugares">
            {suggestions.map((place, i) => (
              <li key={`${place.lat},${place.lng},${place.name}`} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  className={`rec-suggest__item ${i === active ? 'is-active' : ''}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(place)}
                >
                  <span className="rec-suggest__icon">
                    <Pin />
                  </span>
                  <span className="rec-suggest__text">
                    <strong>{place.name}</strong> {place.context}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <form className="rec-ask" onSubmit={search}>
          <button
            type="button"
            className={`rec-ask__icon ${menu ? 'is-on' : ''}`}
            aria-label="Opciones: quiénes van, dulcería, cuándo y presupuesto"
            aria-expanded={menu}
            onClick={() => setMenu((m) => !m)}
          >
            <Sliders />
          </button>
          <input
            className="rec-ask__input"
            type="text"
            value={address}
            onChange={(e) => {
              setAddress(e.target.value);
              setTyping(true);
              setMenu(false);
            }}
            onKeyDown={keys}
            onBlur={() => setSuggestions([])}
            role="combobox"
            aria-expanded={suggestions.length > 0}
            aria-controls="rec-suggest"
            aria-autocomplete="list"
            autoComplete="off"
            placeholder={located ? 'Cambiar punto de partida: calle, colonia o lugar' : '¿Desde dónde sales? Calle, colonia o lugar'}
            aria-label="Dirección o lugar de partida"
          />
          <button type="button" className="rec-ask__locate" onClick={locate} disabled={busy}>
            <Locate />
            <span>Mi ubicación</span>
          </button>
          <button type="submit" className="rec-ask__send" aria-label="Buscar" disabled={busy || !address.trim()}>
            <Send />
          </button>
        </form>
        </div>
        {!located && catalog && catalog.plazas.length > 1 && (
          <div className="rec__chips rec-stage__cities" role="radiogroup" aria-label="Ciudad">
            {catalog.plazas.map(([key, label], i) => (
              <button key={key} type="button" role="radio" aria-checked={plaza === i} className={`rec__chip ${plaza === i ? 'is-on' : ''}`} onClick={() => setPlaza(i)}>
                {label}
              </button>
            ))}
          </div>
        )}
        {!located && <p className="rec-stage__hint">{notice || 'Escribe tu dirección o usa tu ubicación para empezar.'}</p>}
      </div>
    </section>
  );
}
