// Mapa del recomendador. Carga solo en el navegador (next/dynamic). Un clic en un cine lo elige. Un doble clic en otro
// lugar mueve el punto de partida: un clic suelto puede ser accidental. MapLibre con el estilo Positron de OpenFreeMap: no
// pide clave y permite uso comercial. Todos los cines van en tinta, sin color por cadena (design.md §3). El único rojo
// es el punto de partida. Los colores salen de las variables de globals.css.

import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

export const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';
const CIRCLE_STEPS = 64;
const DOUBLE_CLICK_MS = 400;
const DOUBLE_CLICK_PX = 12;

type Point = { lat: number; lng: number };
type Cinema = Point & { id: string; name: string; chain: string };

function circle({ lat, lng }: Point, km: number): GeoJSON.Feature {
  const coords: [number, number][] = [];
  for (let i = 0; i <= CIRCLE_STEPS; i++) {
    const a = (i / CIRCLE_STEPS) * 2 * Math.PI;
    coords.push([lng + (km / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a), lat + (km / 111.32) * Math.sin(a)]);
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } };
}

/** `cubic-bezier(x1, y1, x2, y2)` como función de easing de MapLibre (t → progreso). Resuelve x(s) = t por Newton y
 *  devuelve y(s). */
function cubicBezier(x1: number, y1: number, x2: number, y2: number) {
  const at = (a: number, b: number, s: number) => 3 * a * s * (1 - s) ** 2 + 3 * b * s ** 2 * (1 - s) + s ** 3;
  const slope = (a: number, b: number, s: number) => 3 * a * (1 - s) ** 2 + 6 * (b - a) * s * (1 - s) + 3 * (1 - b) * s ** 2;
  return (t: number) => {
    let s = t;
    for (let i = 0; i < 8; i++) {
      const d = slope(x1, x2, s);
      if (Math.abs(d) < 1e-6) break;
      s = Math.min(1, Math.max(0, s - (at(x1, x2, s) - t) / d));
    }
    return at(y1, y2, s);
  };
}

/** La curva `--ease-out` de globals.css, para que el mapa se mueva como el resto de la página. */
function easeOut() {
  const css = getComputedStyle(document.documentElement).getPropertyValue('--ease-out');
  const n = css.match(/-?[\d.]+/g)?.map(Number);
  return n && n.length === 4 ? cubicBezier(n[0], n[1], n[2], n[3]) : cubicBezier(0.22, 1, 0.36, 1);
}

function collection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: 'FeatureCollection', features };
}

export default function RecommenderMap({
  center,
  start,
  radiusKm,
  cinemas,
  selected = null,
  bottomInset = 0,
  onPick,
  onCinema,
}: {
  center: Point;
  start: Point | null;
  radiusKm: number;
  cinemas: Cinema[];
  selected?: string | null;
  bottomInset?: number;
  onPick: (p: Point) => void;
  onCinema?: (id: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const pick = useRef(onPick);
  const choose = useRef(onCinema);
  const [broken, setBroken] = useState(false);
  pick.current = onPick;
  choose.current = onCinema;

  useEffect(() => {
    if (!box.current) return;
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue('--ink').trim();
    const red = css.getPropertyValue('--red').trim();
    const paper = css.getPropertyValue('--paper').trim();
    const gray = css.getPropertyValue('--gray').trim();
    let m: maplibregl.Map;
    try {
      m = new maplibregl.Map({ container: box.current, style: BASEMAP_STYLE, center: [center.lng, center.lat], zoom: 10.5, attributionControl: false });
    } catch {
      // Sin WebGL no hay mapa. El resto de la página funciona igual.
      setBroken(true);
      return;
    }
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    // OpenFreeMap y OpenStreetMap exigen un crédito visible. Abajo lo tapa el dock.
    m.addControl(new maplibregl.AttributionControl({ compact: true }), 'top-left');
    m.on('load', () => {
      m.addSource('radius', { type: 'geojson', data: collection([]) });
      m.addSource('cinemas', { type: 'geojson', data: collection([]) });
      m.addSource('start', { type: 'geojson', data: collection([]) });
      m.addLayer({ id: 'radius', type: 'line', source: 'radius', paint: { 'line-color': gray, 'line-width': 1 } });
      m.addLayer({
        id: 'cinemas',
        type: 'circle',
        source: 'cinemas',
        paint: {
          'circle-radius': ['case', ['boolean', ['get', 'selected'], false], 10, 7],
          'circle-color': ink,
          'circle-stroke-color': paper,
          'circle-stroke-width': ['case', ['boolean', ['get', 'selected'], false], 3, 1.5],
        },
      });
      m.addLayer({
        id: 'start',
        type: 'circle',
        source: 'start',
        paint: { 'circle-radius': 8, 'circle-color': red, 'circle-stroke-color': paper, 'circle-stroke-width': 3 },
      });
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
      m.on('mouseenter', 'cinemas', (e) => {
        m.getCanvas().style.cursor = 'pointer';
        const f = e.features?.[0];
        if (f) popup.setLngLat(e.lngLat).setText(`${f.properties.name} · ${f.properties.chain}`).addTo(m);
      });
      m.on('mouseleave', 'cinemas', () => {
        m.getCanvas().style.cursor = '';
        popup.remove();
      });
      m.fire('ready');
    });
    // El doble clic sale de dos eventos click y no de dblclick: en celular, el doble toque no siempre da dblclick.
    m.doubleClickZoom.disable();
    let last = { time: -Infinity, x: 0, y: 0 };
    m.on('click', (e) => {
      const hit = m.getLayer('cinemas') ? m.queryRenderedFeatures(e.point, { layers: ['cinemas'] })[0] : undefined;
      if (hit && choose.current) return choose.current(String(hit.properties.id));
      const time = e.originalEvent.timeStamp;
      const double = time - last.time < DOUBLE_CLICK_MS && Math.hypot(e.point.x - last.x, e.point.y - last.y) < DOUBLE_CLICK_PX;
      last = double ? { time: -Infinity, x: 0, y: 0 } : { time, x: e.point.x, y: e.point.y };
      if (double) pick.current({ lat: e.lngLat.lat, lng: e.lngLat.lng });
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const draw = () => {
      (m.getSource('start') as maplibregl.GeoJSONSource).setData(
        collection(start ? [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [start.lng, start.lat] } }] : []),
      );
      (m.getSource('radius') as maplibregl.GeoJSONSource).setData(collection(start ? [circle(start, radiusKm)] : []));
      (m.getSource('cinemas') as maplibregl.GeoJSONSource).setData(
        collection(
          cinemas.map((c) => ({
            type: 'Feature',
            properties: { id: c.id, name: c.name, chain: c.chain, selected: c.id === selected },
            geometry: { type: 'Point', coordinates: [c.lng, c.lat] },
          })),
        ),
      );
    };
    if (m.getSource('start')) draw();
    else m.once('ready', draw);
  }, [start, radiusKm, cinemas, selected]);

  // El centro del mapa no cuenta el área que tapa el dock.
  useEffect(() => {
    map.current?.setPadding({ top: 0, bottom: bottomInset, left: 0, right: 0 });
  }, [bottomInset]);

  // Sin punto de partida, el mapa de fondo sigue a la ciudad elegida.
  useEffect(() => {
    if (start || !map.current) return;
    map.current.jumpTo({ center: [center.lng, center.lat], zoom: 10.5 });
  }, [center.lat, center.lng, start]);

  useEffect(() => {
    if (!start || !map.current) return;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    map.current.easeTo({
      center: [start.lng, start.lat],
      zoom: Math.max(map.current.getZoom(), 12.5),
      padding: { top: 0, bottom: bottomInset, left: 0, right: 0 },
      duration: still ? 0 : 900,
      easing: easeOut(),
    });
  }, [start, bottomInset]);

  if (broken)
    return (
      <p className="rec__notice">
        Tu navegador no puede mostrar el mapa. Escribe una dirección o usa tu ubicación: los resultados funcionan igual.
      </p>
    );
  return <div ref={box} className="rec__map" role="application" aria-label="Mapa: haz doble clic para mover tu punto de partida" />;
}
