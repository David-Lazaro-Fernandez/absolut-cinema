'use client';

// "¿A dónde ir?": funciones cerca del visitante que caben en el presupuesto de su grupo. La API (`lib/api.ts`) responde
// cada búsqueda. La página no recibe el catálogo completo.

import dynamic from 'next/dynamic';
import { type CSSProperties, type ReactNode, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { preconnect } from 'react-dom';
import { API_URL, searchParams, useApi } from '@/lib/api';
import { type PlacesFile, buildIndex, makePlace, plain, searchPlaces } from '@/lib/places';
import { FooterSection } from '@/components/footer-section';
import { Calendar, Close, Locate, People, Pin, Popcorn, Send, Sliders, Wallet } from '@/components/rec-icons';
import {
  type Combo,
  type Options,
  type Promo,
  type Query,
  type Row,
  type Search,
  type SnackItem,
  type Snacks,
  type Sort,
  FORMAT_LABEL,
  LANGUAGE_LABEL,
  SNACK_LABEL,
  SORT_LABEL,
  nearestPlaza,
  nowIn,
  startMinutes,
} from '@/lib/recommend';

const RecommenderMap = dynamic(() => import('@/components/recommender-map'), { ssr: false });

const PLACES_URL = '/lugares.json'; // De scripts/export_places.py. Sin él, solo sugiere el geocodificador.
// Photon (komoot, datos de OpenStreetMap) permite sugerir mientras se escribe y no pide clave. Nominatim lo prohíbe.
// La instancia pública es de uso justo: con tráfico real, usar una instancia propia.
const GEOCODER = 'https://photon.komoot.io/api/';
const DEFAULT_CENTER = { lat: 19.4326, lng: -99.1332 }; // CDMX, hasta que cargan las opciones
const API_MAX_PEOPLE = 20;
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
const KEYBOARD_MIN = 120; // px; menos es la barra del navegador que se esconde, no el teclado

type Point = { lat: number; lng: number; label: string };

const siteKey = (p: { lat: number; lng: number }) => `${p.lat},${p.lng}`;
const rowKey = (r: Row) => `${r.chain}-${r.show_id}`;

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

function Counter({ label, value, max, onChange }: { label: string; value: number; max: number; onChange: (v: number) => void }) {
  return (
    <div className="rec__counter">
      <span className="rec__label">{label}</span>
      <div className="rec__stepper">
        <button type="button" aria-label={`Menos ${label.toLowerCase()}`} onClick={() => onChange(Math.max(0, value - 1))}>
          −
        </button>
        <output>{value}</output>
        <button type="button" aria-label={`Más ${label.toLowerCase()}`} onClick={() => onChange(Math.min(max, value + 1))}>
          +
        </button>
      </div>
    </div>
  );
}

// Un cine que no vende en línea lo dice en el lugar del enlace de compra, con el porqué en el globo.
const BOX_OFFICE_ABOUT = 'Este cine no vende boletos en línea. Se compran en su taquilla.';

function BuyLink({ row, chain }: { row: Row; chain: string }) {
  if (row.box_office_only)
    return (
      <span className="rec__buy rec__buy--box-office">
        <Tip label="Solo en taquilla" about={BOX_OFFICE_ABOUT} />
      </span>
    );
  if (!row.buy_url) return null;
  return (
    <a className="rec__buy" href={row.buy_url} target="_blank" rel="noopener noreferrer" aria-label={`Comprar en ${chain} (abre su sitio)`}>
      Comprar ↗
    </a>
  );
}

function Pick({ label, value, row, chain, today }: { label: string; value: string; row: Row; chain: string; today: string }) {
  return (
    <div className="rec-pick">
      <span className="rec-pick__label">{label}</span>
      <strong className="rec-pick__value">{value}</strong>
      <span className="rec-pick__cinema">
        {row.cinema_name} · {chain}
      </span>
      <span className="rec-pick__show">
        {row.title} · {row.date === today ? time12(startMinutes(row)) : `${dayLabel(row.date, today)}, ${time12(startMinutes(row))}`}
      </span>
      <BuyLink row={row} chain={chain} />
    </div>
  );
}

// "2 × Combo Clásico + Palomitas y refresco": el desglose de la dulcería de una función.
const ITEM_CHARS = 16;
const itemsText = (items: SnackItem[], max = Infinity) =>
  items.map((i) => `${i.units > 1 ? `${i.units} × ` : ''}${clip(i.name, max)}`).join(' + ');

// La promoción del día: si ya va en el total, "incluye Combo Lunes"; si no, la alternativa para 2 con su precio.
const promoPrice = (p: Promo) => (p.price_max ? `${money(p.price)} o ${money(p.price_max)}` : money(p.price));

// El globo que explica un término (el programa Loop o Club Cinépolis, la venta solo en taquilla). Va en
// `position: fixed` porque la tabla recorta lo que sobresale (`overflow-x: auto`). Abre con el cursor y con el foco,
// así que en celular abre al tocarlo.
const TIP_HALF = 130;
function Tip({ label, about }: { label: string; about: string }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  const open = (e: { currentTarget: HTMLElement }) => {
    const box = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max(box.left + box.width / 2, TIP_HALF), window.innerWidth - TIP_HALF);
    setAt({ x, y: box.top });
  };
  const close = () => setAt(null);
  return (
    <span className="rec__tip" tabIndex={0} aria-label={`${label}: ${about}`}
      onMouseEnter={open} onFocus={open} onMouseLeave={close} onBlur={close}>
      {label}
      {at && <span role="tooltip" className="rec__bubble" style={{ left: at.x, top: at.y }}>{about}</span>}
    </span>
  );
}

// La columna Promoción: el nombre y, en gris, si ya va en el total o cuánto cuesta para 2, y qué programa pide.
function PromoCell({ promo }: { promo: Promo }) {
  return (
    <>
      <span title={`${promo.includes}. ${promo.condition}`}>{promo.name}</span>
      <span className="rec__items">
        {promo.applied ? 'en el total' : `${promoPrice(promo)} para ${promo.people}`}
        {promo.program && promo.program_about && (
          <> · con <Tip label={promo.program} about={promo.program_about} /></>
        )}
      </span>
    </>
  );
}

// "2 a 3 personas", "1 niño", "2 adultos": a quién cubre un combo.
function comboPeople(c: Combo) {
  const n = c.min === c.max ? `${c.max}` : `${c.min} a ${c.max}`;
  const who = { all: ['persona', 'personas'], children: ['niño', 'niños'], adults: ['adulto', 'adultos'] }[c.for];
  return `${n} ${c.max === 1 ? who[0] : who[1]}`;
}

function ShowsTable({
  rows,
  withSnacks,
  today,
  chains,
  partial,
}: {
  rows: Row[];
  withSnacks: boolean;
  today: string;
  chains: Record<string, string>;
  partial?: boolean;
}) {
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
            <th>Promoción</th>
            {!partial && <th className="num">Dulcería</th>}
            {!partial && <th className="num">Total</th>}
            <th className="num">Distancia</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              <td className="rec__c-cinema">
                <strong>{r.cinema_name}</strong>
                <span className="rec__chain">{chains[r.chain]}</span>
              </td>
              <td className="rec__c-title">
                <p className="rec__movie" title={r.title}>{r.title}</p>
              </td>
              <td className="num rec__c-time">
                {r.date === today ? time12(startMinutes(r)) : `${dayLabel(r.date, today)}, ${time12(startMinutes(r))}`}
                <BuyLink row={r} chain={chains[r.chain]} />
              </td>
              <td className="rec__c-format">
                {FORMAT_LABEL[r.format_bucket] ?? r.format_bucket}
                <span className="rec__chain">{LANGUAGE_LABEL[r.language] ?? r.language}</span>
              </td>
              <td className="num rec__c-tickets" data-label="Boletos">
                {r.tickets_total !== null ? money(r.tickets_total) : '—'}
              </td>
              <td className={`rec__c-promo${r.promo ? '' : ' rec__c-promo--none'}`} data-label="Promoción">
                {r.promo ? <PromoCell promo={r.promo} /> : '—'}
              </td>
              {!partial && (
                <td className="num rec__c-snacks" data-label="Dulcería">
                  {withSnacks ? (
                    <>
                      {money(r.snacks_total!)}
                      {r.snacks_items && r.snacks_items.length > 0 && <span className="rec__items" title={itemsText(r.snacks_items)}>{itemsText(r.snacks_items, ITEM_CHARS)}</span>}
                    </>
                  ) : r.snack_reference !== null
                      ? <span className="rec__ref" title="Palomitas y refresco para una persona, como referencia">ref. {money(r.snack_reference)}</span>
                      : <span className="rec__ref">sin precio en sala</span>}
                </td>
              )}
              {!partial && <td className="num rec__total rec__c-total">{money(r.total!)}</td>}
              <td className="num rec__c-dist">{km(r.distance_km)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type RowId = 'group' | 'snacks' | 'when' | 'budget' | 'more';
type Tab = 'complete' | 'snacks_unpriced' | 'unpriced';
const PAGE = 20; // funciones por página en la pantalla de resultados

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

// En celular el menú de opciones es una hoja inferior; en escritorio, un menú pegado a la barra. Mismo corte que el CSS.
const PHONE = '(max-width: 700px)';
const onPhoneChange = (notify: () => void) => {
  const query = window.matchMedia(PHONE);
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
};

function usePhone() {
  return useSyncExternalStore(onPhoneChange, () => window.matchMedia(PHONE).matches, () => false);
}

// En celular la barra deja poco ancho al campo de dirección: su texto guía se corta en 26 caracteres.
const PHONE_HINT_CHARS = 26;
const clip = (text: string, max: number) => (text.length > max ? `${text.slice(0, max).trimEnd()}…` : text);

export function Recommender() {
  const [start, setStart] = useState<Point | null>(null);
  const [address, setAddress] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState(0);
  const [seniors, setSeniors] = useState(0);
  const [budget, setBudget] = useState('');
  const [snacks, setSnacks] = useState<Snacks>('none');
  const [combo, setCombo] = useState<string | null>(null);   // un combo elegido de la lista manda sobre `snacks`
  const withSnacks = snacks !== 'none' || combo !== null;
  const snackPlan = combo ?? SNACK_LABEL[snacks].toLowerCase();
  const [date, setDate] = useState('');
  const [hours, setHours] = useState('Todo el día');
  const [radiusKm, setRadiusKm] = useState(5);
  const [title, setTitle] = useState<string | null>(null);
  const [format, setFormat] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>('distance');
  const [open, setOpen] = useState<RowId | null>(null);
  const [menu, setMenu] = useState(false);
  const [view, setView] = useState<'search' | 'results'>('search');
  const [siteId, setSiteId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [placesFile, setPlacesFile] = useState<PlacesFile | null>(null);
  const [active, setActive] = useState(-1);
  const [typing, setTyping] = useState(false);
  const [tab, setTab] = useState<Tab>('complete');
  const [shown, setShown] = useState(PAGE);
  const [plazaIndex, setPlazaIndex] = useState(0);
  const menuBox = useRef<HTMLDivElement>(null);
  const phone = usePhone();
  // Cada minuto: con la página abierta, una función que ya empezó sale de los resultados.
  const [now, setNow] = useState(() => nowIn());
  useEffect(() => {
    const timer = setInterval(() => setNow(nowIn()), 60_000);
    return () => clearInterval(timer);
  }, []);
  const toggle = (id: RowId) => setOpen((o) => (o === id ? null : id));
  const { data: options, error: optionsError } = useApi<Options>('/v1/a-donde-ir/opciones', useMemo(() => new URLSearchParams(), []), now.date);
  const area = options?.plazas[plazaIndex];
  const scope = area?.plaza ?? '';
  const bbox = area ? area.bbox.join(',') : '';
  const center = useMemo(() => (area ? { lat: area.lat, lng: area.lng } : DEFAULT_CENTER), [area]);
  const chains = useMemo(() => Object.fromEntries((options?.cinemas ?? []).map((c) => [c.chain, c.chain_label])), [options]);

  // Con punto de partida, la plaza es la más cercana a él.
  useEffect(() => {
    if (options && start) setPlazaIndex(nearestPlaza(options.plazas, start.lat, start.lng));
  }, [options, start]);

  useEffect(() => {
    if (!menu) return;
    // En celular la hoja no está dentro del dock: la cierra su velo.
    const outside = (e: MouseEvent) => {
      if (!phone && menuBox.current && !menuBox.current.contains(e.target as Node)) setMenu(false);
    };
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false);
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [menu, phone]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
    setShown(PAGE);
  }, [view, tab]);

  // En celular la barra queda sobre el teclado y el mapa conserva su alto. iOS también achica innerHeight con el
  // teclado: por eso se compara con el alto visible más grande. iOS desplaza la vista al enfocar el campo: por eso la
  // barra va al borde inferior de lo visible en coordenadas del documento. Con zoom, el alto visible no es teclado.
  const stage = useRef<HTMLElement>(null);
  const [keyboard, setKeyboard] = useState(0);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [short, setShort] = useState(false);
  const docked = view === 'search' && Boolean(start);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv || !docked) return;
    let tallest = Math.max(window.innerHeight, vv.height);
    let width = vv.width;
    const fit = () => {
      if (vv.width !== width) [tallest, width] = [vv.height, vv.width];
      tallest = Math.max(tallest, vv.height);
      const zoomed = vv.scale > 1;
      const open = !zoomed && tallest - vv.height > KEYBOARD_MIN;
      const el = stage.current;
      const bottom = el ? el.offsetTop + el.offsetHeight : tallest;
      setKeyboardOpen(open);
      setKeyboard(open ? Math.max(0, Math.round(bottom - vv.pageTop - vv.height)) : 0);
      setShort(!zoomed && vv.height < tallest / 2);
    };
    vv.addEventListener('resize', fit);
    vv.addEventListener('scroll', fit);
    window.addEventListener('scroll', fit, { passive: true });
    return () => {
      vv.removeEventListener('resize', fit);
      vv.removeEventListener('scroll', fit);
      window.removeEventListener('scroll', fit);
      setKeyboard(0);
      setKeyboardOpen(false);
      setShort(false);
    };
  }, [docked]);

  // Un enlace con ?lat=19.35&lng=-99.16 abre la página con ese punto de partida.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const lat = Number(q.get('lat'));
    const lng = Number(q.get('lng'));
    if (q.has('lat') && q.has('lng') && Number.isFinite(lat) && Number.isFinite(lng))
      setStart({ lat, lng, label: 'el punto del enlace' });
  }, []);

  useEffect(() => {
    if (!options) return;
    setDate((d) => {
      const dates = options.dates.map((x) => x.date);
      return dates.includes(d) ? d : dates.includes(now.date) ? now.date : dates[0] ?? '';
    });
  }, [options, now.date]);

  // Abre las conexiones antes de la primera búsqueda. En una red lenta, el saludo TLS es buena parte de la espera.
  useEffect(() => {
    preconnect(new URL(GEOCODER).origin);
    preconnect(new URL(API_URL).origin);
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
        (options?.cinemas ?? []).map((c) => ({ name: c.cinema_name, chain: c.chain_label, lat: c.lat, lng: c.lng })),
      ),
    [placesFile, options],
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

  const days = useMemo(() => (options ? options.dates.map((d) => d.date).filter((d) => d >= now.date) : []), [options, now.date]);
  const people = adults + children + seniors;
  const budgetValue = Number(budget.replace(/[^\d]/g, ''));
  const query = useMemo<Query | null>(
    () =>
      start && people && date
        ? {
            lat: start.lat,
            lng: start.lng,
            date,
            adults,
            children,
            seniors,
            snacks,
            combo,
            budget: budgetValue > 0 ? budgetValue : null,
            radiusKm,
            hours: HOURS[hours],
            title,
            format,
            sort,
          }
        : null,
    [start, people, date, adults, children, seniors, snacks, combo, budgetValue, radiusKm, hours, title, format, sort],
  );
  const searched = useApi<Search>('/v1/a-donde-ir/funciones', useMemo(() => (query ? searchParams(query) : null), [query]), now.minutes);
  const result = searched.data;
  const titles = result?.titles ?? [];
  // Un punto por edificio: el complejo y su sala Platino o VIP comparten coordenadas, y un punto tapaba al otro.
  const sites = useMemo(
    () =>
      (result?.sites ?? []).map((s) => ({
        id: siteKey(s),
        lat: s.lat,
        lng: s.lng,
        names: s.cinemas.map((c) => c.cinema_name),
        name: s.cinemas.map((c) => c.cinema_name).join(' · '),
        chain: [...new Set(s.cinemas.map((c) => c.chain_label))].join(' · '),
        distanceKm: s.distance_km,
      })),
    [result],
  );
  const site = sites.find((s) => s.id === siteId) ?? null;
  // La búsqueda trae pocas funciones por cine. La ficha pide todas las del edificio.
  const siteSearch = useApi<Search>(
    '/v1/a-donde-ir/funciones',
    useMemo(() => (query && site ? searchParams({ ...query, site }) : null), [query, site]),
    now.minutes,
    0,
  );
  const siteRows = useMemo(
    () =>
      [...(siteSearch.data?.complete ?? []), ...(siteSearch.data?.snacks_unpriced ?? [])]
        .filter((r) => siteKey(r) === siteId) // Mientras carga, `data` es del edificio anterior.
        .sort((a, b) => a.datetime_local.localeCompare(b.datetime_local)),
    [siteSearch.data, siteId],
  );
  const siteLoading = siteSearch.loading && siteRows.length === 0;

  function choose(place: Suggestion) {
    setStart({ lat: place.lat, lng: place.lng, label: place.context ? `${place.name}, ${place.context}` : place.name });
    setAddress(place.name);
    setSuggestions([]);
    setTyping(false);
    setSiteId(null);
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
  const lists: Record<Tab, Row[]> = {
    complete: result?.complete ?? [],
    snacks_unpriced: withSnacks ? result?.snacks_unpriced ?? [] : [],
    unpriced: result?.unpriced ?? [],
  };
  const counts: Record<Tab, number> = {
    complete: result?.summary.shows ?? 0,
    snacks_unpriced: result?.summary.snacks_unpriced ?? 0,
    unpriced: result?.summary.unpriced ?? 0,
  };
  const tabs: [Tab, string][] = [
    ['complete', 'Con costo completo'],
    ['snacks_unpriced', 'Sin precio de dulcería'],
    ['unpriced', 'Sin precio de boletos'],
  ];
  const ready = options && start && people;
  const cheapest = result?.summary.cheapest;
  const nearest = result?.summary.nearest;

  if (view === 'results' && ready && result) {
    const rows = lists[tab];
    return (
      <>
      <section className="rec-screen">
        <div className="rec-screen__bar">
          <button type="button" className="pill pill--ghost pill--sm" onClick={() => setView('search')}>
            ← Cambiar búsqueda
          </button>
          <span className="rec-screen__plan">
            {groupText(adults, children, seniors)} · {snackPlan} · {dayLabel(date, now.date).toLowerCase()}
            {budgetValue > 0 ? ` · hasta ${money(budgetValue)}` : ''}
          </span>
        </div>
        <h1 className="rec-screen__title">Funciones para {groupText(adults, children, seniors)}</h1>
        {result.complete.length ? (
          <>
            <div className="rec-picks">
              {cheapest && (
                <Pick
                  label={`La más barata · a ${km(cheapest.distance_km)}`}
                  value={`${money(cheapest.total!)} en total`}
                  row={cheapest}
                  chain={chains[cheapest.chain]}
                  today={now.date}
                />
              )}
              {nearest && (
                <Pick
                  label="La más cercana"
                  value={`a ${km(nearest.distance_km)}`}
                  row={nearest}
                  chain={chains[nearest.chain]}
                  today={now.date}
                />
              )}
            </div>
            <p className="rec__lead">
              {result.summary.cinemas} {result.summary.cinemas === 1 ? 'cine tiene' : 'cines tienen'} funciones que caben
              {budgetValue > 0 ? ' en tu presupuesto' : ''} a {radiusKm} km o menos de tu punto de partida.
            </p>
          </>
        ) : (
          <p className="rec__lead">
            Ninguna función con costo completo cabe con esos filtros. Cambia la búsqueda: más distancia, otro horario, otra dulcería o más
            presupuesto.
          </p>
        )}

        {(lists.snacks_unpriced.length > 0 || lists.unpriced.length > 0) && (
        <div className="rec-tabs" role="tablist">
          {tabs
            .filter(([t]) => t === 'complete' || lists[t].length > 0)
            .map(([t, label]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} className={`rec-tabs__tab ${tab === t ? 'is-on' : ''}`} onClick={() => setTab(t)}>
                {label} {t !== 'complete' && <span>{counts[t].toLocaleString('es-MX')}</span>}
              </button>
            ))}
        </div>
        )}

        {tab === 'snacks_unpriced' && (
          <p className="rec__hint">
            Estos cines no publican el precio de su dulcería en sala: solo sabemos cuánto cuestan los boletos y no los comparamos con los que caben.
          </p>
        )}
        {tab === 'unpriced' && <p className="rec__hint">No hay precio de lista de su cine para ese formato y día; por eso no entran al presupuesto.</p>}

        {rows.length > 0 && (
          <ShowsTable rows={rows.slice(0, shown)} withSnacks={withSnacks} today={now.date} chains={chains} partial={tab !== 'complete'} />
        )}
        {rows.length > shown && (
          <button type="button" className="pill pill--ghost rec-screen__more" onClick={() => setShown((n) => n + PAGE)}>
            Ver {Math.min(PAGE, rows.length - shown)} más
          </button>
        )}

        <p className="rec__source">
          Powered by: Matiné, Photon (komoot) © OpenStreetMap. Mapa © OpenFreeMap y OpenStreetMap.
        </p>
      </section>
      <FooterSection />
      </>
    );
  }

  const located = Boolean(start);
  const menuRows = (
    <div
      className={`rec-menu ${phone ? 'rec-menu--sheet' : located ? '' : 'rec-menu--down'} ${menu ? 'is-open' : ''}`}
      role={phone ? 'dialog' : 'menu'}
      aria-modal={phone || undefined}
      aria-label="Opciones de la búsqueda"
      inert={!menu}
    >
      {phone && (
        <>
          <span className="rec-menu__handle" aria-hidden="true" />
          <p className="rec-menu__title" aria-hidden="true">Opciones</p>
        </>
      )}
      <div className="rec-menu__inner">
      <MenuRow id="group" open={open} onToggle={toggle} icon={<People />} label="Quiénes van" value={groupText(adults, children, seniors)}>
        <div className="rec__row">
          <Counter label="Adultos" value={adults} max={API_MAX_PEOPLE - children - seniors} onChange={setAdults} />
          <Counter label="Niños" value={children} max={API_MAX_PEOPLE - adults - seniors} onChange={setChildren} />
          <Counter label="Adultos mayores" value={seniors} max={API_MAX_PEOPLE - adults - children} onChange={setSeniors} />
        </div>
      </MenuRow>
      <MenuRow id="snacks" open={open} onToggle={toggle} icon={<Popcorn />} label="Dulcería" value={combo ?? SNACK_LABEL[snacks]}>
        <div className="rec__chips" role="radiogroup" aria-label="Dulcería">
          {(options?.snacks ?? (Object.keys(SNACK_LABEL) as Snacks[])).map((k) => {
            const on = combo === null && snacks === k;
            return (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={on}
                className={`rec__chip ${on ? 'is-on' : ''}`}
                onClick={() => {
                  setSnacks(k);
                  setCombo(null);
                }}
              >
                {SNACK_LABEL[k]}
              </button>
            );
          })}
        </div>
        <label className="rec__field">
          <span className="rec__label">O elige un combo</span>
          <select value={combo ?? ''} onChange={(e) => setCombo(e.target.value || null)}>
            <option value="">Ninguno en particular</option>
            {(options?.combos ?? []).map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} · {comboPeople(c)}
              </option>
            ))}
          </select>
        </label>
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
            <select value={title ?? ''} onChange={(e) => setTitle(e.target.value || null)}>
              <option value="">Cualquier película</option>
              {titles.map((t) => (
                <option key={t.title_norm} value={t.title_norm}>
                  {t.title}
                </option>
              ))}
            </select>
          </label>
          <label className="rec__field">
            <span className="rec__label">Formato</span>
            <select value={format ?? ''} onChange={(e) => setFormat(e.target.value || null)}>
              <option value="">Cualquier formato</option>
              {(options?.formats ?? []).map((f) => (
                <option key={f} value={f}>
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
    </div>
  );

  return (
    <section
      ref={stage}
      className={`rec-stage ${located ? 'is-located' : ''} ${keyboardOpen ? 'is-typing' : ''} ${short ? 'is-short' : ''}`}
      style={{ '--keyboard': `${keyboard}px` } as CSSProperties}
    >
      <div className="rec-stage__map">
        <RecommenderMap
          center={center}
          start={start}
          radiusKm={radiusKm}
          cinemas={sites}
          selected={siteId}
          bottomInset={located ? MAP_OVERLAP : 0}
          onPick={(p) => {
            setSiteId(null);
            setStart({ ...p, label: 'el punto que marcaste en el mapa' });
          }}
          onCinema={setSiteId}
        />
      </div>
      {/* Sin punto de partida, el velo tapa el mapa y bloquea los clics. */}
      <div className="rec-stage__glass" aria-hidden="true" />

      {!located && <h1 className="rec-stage__title">¿A dónde vamos al cine hoy?</h1>}

      {located && site && (siteRows.length > 0 || siteLoading) && (
        <aside className="rec-card" aria-label={`Funciones en ${site.name}`} aria-busy={siteLoading}>
          <div className="rec-card__head">
            <div>
              <strong>{site.name}</strong>
              <span className="rec__chain">
                {site.chain} · {km(site.distanceKm)}
                {!siteLoading && ` · ${siteRows.length} ${siteRows.length === 1 ? 'función' : 'funciones'}`}
              </span>
            </div>
            <button type="button" className="rec-card__close" aria-label="Cerrar" onClick={() => setSiteId(null)}>
              <Close />
            </button>
          </div>
          <ul className="rec-card__list">
            {siteLoading &&
              [0, 1, 2, 3].map((i) => (
                <li key={i} className="rec-card__skeleton" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </li>
              ))}
            {siteRows.map((r) => (
              <li key={rowKey(r)}>
                <span className="rec-card__time">
                  {time12(startMinutes(r))}
                  <BuyLink row={r} chain={chains[r.chain]} />
                </span>
                <span className="rec-card__title">
                  {r.title}
                  <span className="rec__chain">
                    {site.names.length > 1 && `${r.cinema_name} · `}
                    {FORMAT_LABEL[r.format_bucket] ?? r.format_bucket} · {LANGUAGE_LABEL[r.language] ?? r.language}
                  </span>
                </span>
                <span className="rec-card__price">
                  {r.total !== null ? money(r.total) : money(r.tickets_total!)}
                  {r.total === null && <span className="rec__chain">solo boletos</span>}
                </span>
              </li>
            ))}
          </ul>
        </aside>
      )}

      {phone && (
        <>
          <div className={`rec-menu__scrim ${menu ? 'is-open' : ''}`} aria-hidden="true" onClick={() => setMenu(false)} />
          {menuRows}
        </>
      )}
      <div className="rec-dock" ref={menuBox}>
        {!phone && menuRows}
        {located && (
          <div className="rec-dock__context">
            <span className="rec-dock__plan">
              {optionsError || searched.error || siteSearch.error
                ? optionsError || searched.error || siteSearch.error
                : !options
                  ? 'Cargando cartelera…'
                  : notice
                    ? notice
                    : !people
                      ? 'Agrega al menos una persona en las opciones.'
                      : !result
                        ? 'Buscando funciones…'
                        : `${groupText(adults, children, seniors)} · ${snackPlan} · toca un cine para ver sus funciones`}
            </span>
            {options && people > 0 && result && (
              <button
                type="button"
                className="pill pill--primary pill--sm"
                aria-busy={searched.loading}
                onClick={() => { setTab('complete'); setView('results'); }}
              >
                {result.summary.cinemas
                  ? `Ver funciones en ${result.summary.cinemas} ${result.summary.cinemas === 1 ? 'cine' : 'cines'}`
                  : 'Ver resultados'}
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
            placeholder={clip(
              located ? 'Cambiar punto de partida: calle, colonia o lugar' : '¿Desde dónde sales? Calle, colonia o lugar',
              phone ? PHONE_HINT_CHARS : Infinity,
            )}
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
        {!located && options && options.plazas.length > 1 && (
          <div className="rec__chips rec-stage__cities" role="radiogroup" aria-label="Ciudad">
            {options.plazas.map((p, i) => (
              <button key={p.plaza} type="button" role="radio" aria-checked={plazaIndex === i} className={`rec__chip ${plazaIndex === i ? 'is-on' : ''}`} onClick={() => setPlazaIndex(i)}>
                {p.label}
              </button>
            ))}
          </div>
        )}
        {!located && <p className="rec-stage__hint">{notice || optionsError || 'Escribe tu dirección o usa tu ubicación para empezar.'}</p>}
      </div>
    </section>
  );
}
