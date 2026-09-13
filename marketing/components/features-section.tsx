'use client';

import { Reveal, useReveal } from './reveal';

const FEATURES = [
  {
    number: '01',
    title: 'Cambios de última hora',
    text:
      'Funciones que se cancelan o se mueven de sala u horario horas antes de empezar. Con tres capturas al día sabes cuándo pasó, en qué cine y con qué frecuencia se repite.',
    Visual: TimelineVisual,
  },
  {
    number: '02',
    title: 'Comparación por porcentajes, no en bruto',
    text:
      'Tu competencia tiene distinto número de cines y salas. Cada medida es el porcentaje de la programación de cada cadena, por franja, formato e idioma: la única comparación que no engaña.',
    Visual: SharesVisual,
  },
  {
    number: '03',
    title: 'El día de hoy, comparable',
    text:
      'Algunas cadenas borran cada función al empezar; otras la conservan horas. Toda consulta que incluye hoy recorta desde el mismo momento para las dos, así nadie gana por conservar más historial.',
    Visual: TodayVisual,
  },
  {
    number: '04',
    title: 'Precio, aforo y dulcería',
    text:
      'Boleto por formato y tipo de día, butacas por sala medidas en el plano de asientos, menú de dulcería en sala y a domicilio. Datos que existen en la API de cada cadena y nadie sigue en el tiempo.',
    Visual: PricesVisual,
  },
];

function TimelineVisual() {
  return (
    <svg viewBox="0 0 200 160" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="20" y1="96" x2="180" y2="96" opacity="0.3" />
      {[20, 52, 84, 116, 148, 180].map((x) => (
        <line key={x} x1={x} y1="90" x2={x} y2="102" opacity="0.3" />
      ))}
      <rect x="44" y="60" width="28" height="22" rx="3" strokeDasharray="4 4" opacity="0.35" />
      <rect x="44" y="60" width="28" height="22" rx="3" fill="currentColor" stroke="none">
        <animate
          attributeName="x"
          values="44;44;116;116;44"
          keyTimes="0;0.3;0.5;0.9;1"
          calcMode="spline"
          keySplines="0.22 1 0.36 1;0.22 1 0.36 1;0.22 1 0.36 1;0.22 1 0.36 1"
          dur="5s"
          repeatCount="indefinite"
        />
      </rect>
      <g transform="translate(148 60)">
        <rect width="28" height="22" rx="3">
          <animate attributeName="opacity" values="1;1;0.25;0.25;1" keyTimes="0;0.55;0.7;0.95;1" dur="5s" repeatCount="indefinite" />
        </rect>
        <path d="M8 5 20 17M20 5 8 17" strokeLinecap="round" opacity="0">
          <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;0.55;0.7;0.95;1" dur="5s" repeatCount="indefinite" />
        </path>
      </g>
      {[20, 84, 148].map((x, i) => (
        <circle key={x} cx={x} cy="128" r="3" fill="currentColor" stroke="none">
          <animate attributeName="opacity" values="0.3;1;0.3" dur="2s" begin={`${i * 0.6}s`} repeatCount="indefinite" />
        </circle>
      ))}
    </svg>
  );
}

function SharesVisual() {
  return (
    <svg viewBox="0 0 200 160" fill="currentColor">
      <g className="us" transform="translate(20 40)">
        <rect y="0" height="22" rx="3" x="0" width="72" opacity="0.9">
          <animate attributeName="width" values="72;96;72" dur="4s" repeatCount="indefinite" />
        </rect>
        <rect y="0" height="22" rx="3" x="76" width="48" opacity="0.45">
          <animate attributeName="x" values="76;100;76" dur="4s" repeatCount="indefinite" />
          <animate attributeName="width" values="48;36;48" dur="4s" repeatCount="indefinite" />
        </rect>
        <rect y="0" height="22" rx="3" x="128" width="32" opacity="0.15">
          <animate attributeName="x" values="128;140;128" dur="4s" repeatCount="indefinite" />
          <animate attributeName="width" values="32;20;32" dur="4s" repeatCount="indefinite" />
        </rect>
      </g>
      <g transform="translate(20 98)">
        <rect y="0" height="22" rx="3" x="0" width="52" opacity="0.9">
          <animate attributeName="width" values="52;40;52" dur="4s" repeatCount="indefinite" />
        </rect>
        <rect y="0" height="22" rx="3" x="56" width="64" opacity="0.45">
          <animate attributeName="x" values="56;44;56" dur="4s" repeatCount="indefinite" />
          <animate attributeName="width" values="64;72;64" dur="4s" repeatCount="indefinite" />
        </rect>
        <rect y="0" height="22" rx="3" x="124" width="36" opacity="0.15">
          <animate attributeName="x" values="124;120;124" dur="4s" repeatCount="indefinite" />
          <animate attributeName="width" values="36;40;36" dur="4s" repeatCount="indefinite" />
        </rect>
      </g>
      <line x1="100" y1="28" x2="100" y2="132" stroke="currentColor" strokeWidth="1" strokeDasharray="3 4" opacity="0.4" />
      <line x1="180" y1="28" x2="180" y2="132" stroke="currentColor" strokeWidth="1" opacity="0.25" />
    </svg>
  );
}

function TodayVisual() {
  return (
    <svg viewBox="0 0 200 160" fill="none" stroke="currentColor" strokeWidth="2">
      <g className="us">
        <rect x="20" y="48" width="160" height="22" rx="3" />
        {[30, 58, 86, 114, 142].map((x) => (
          <rect key={x} x={x} y="53" width="18" height="12" rx="2" fill="currentColor" stroke="none" opacity="0.8" />
        ))}
        <rect x="20" y="48" height="22" rx="3" fill="currentColor" stroke="none" opacity="0.15" width="0">
          <animate attributeName="width" values="0;160" dur="6s" repeatCount="indefinite" />
        </rect>
      </g>
      <rect x="20" y="90" width="160" height="22" rx="3" />
      {[38, 72, 100, 130, 156].map((x) => (
        <rect key={x} x={x} y="95" width="18" height="12" rx="2" fill="currentColor" stroke="none" opacity="0.8" />
      ))}
      <rect x="20" y="90" height="22" rx="3" fill="currentColor" stroke="none" opacity="0.15" width="0">
        <animate attributeName="width" values="0;160" dur="6s" repeatCount="indefinite" />
      </rect>
      <line x1="20" y1="36" x2="20" y2="124">
        <animate attributeName="x1" values="20;180" dur="6s" repeatCount="indefinite" />
        <animate attributeName="x2" values="20;180" dur="6s" repeatCount="indefinite" />
      </line>
      <circle cx="20" cy="32" r="3" fill="currentColor" stroke="none">
        <animate attributeName="cx" values="20;180" dur="6s" repeatCount="indefinite" />
      </circle>
    </svg>
  );
}

function PricesVisual() {
  const bars = [
    { x: 28, h: [60, 72] },
    { x: 58, h: [84, 70] },
    { x: 88, h: [48, 58] },
    { x: 118, h: [96, 88] },
    { x: 148, h: [70, 80] },
  ];
  return (
    <svg viewBox="0 0 200 160" fill="currentColor">
      <line x1="20" y1="132" x2="180" y2="132" stroke="currentColor" strokeWidth="2" opacity="0.3" />
      {bars.map((b, i) => (
        <rect key={b.x} x={b.x} width="24" rx="2" y={132 - b.h[0]} height={b.h[0]} opacity={i % 2 ? 0.35 : 0.9}>
          <animate attributeName="height" values={`${b.h[0]};${b.h[1]};${b.h[0]}`} dur="4s" repeatCount="indefinite" />
          <animate attributeName="y" values={`${132 - b.h[0]};${132 - b.h[1]};${132 - b.h[0]}`} dur="4s" repeatCount="indefinite" />
        </rect>
      ))}
      <line x1="20" y1="70" x2="180" y2="70" stroke="currentColor" strokeWidth="1" strokeDasharray="3 4" opacity="0.5">
        <animate attributeName="y1" values="70;64;70" dur="4s" repeatCount="indefinite" />
        <animate attributeName="y2" values="70;64;70" dur="4s" repeatCount="indefinite" />
      </line>
      {[40, 70, 100, 130, 160].map((x) => (
        <circle key={x} cx={x} cy="148" r="2.5" opacity="0.4" />
      ))}
    </svg>
  );
}

function FeatureRow({ feature, index }: { feature: (typeof FEATURES)[number]; index: number }) {
  const { ref, visible } = useReveal<HTMLDivElement>(0.2);
  const { Visual } = feature;
  return (
    <div ref={ref} className={`feat__row reveal ${visible ? 'is-visible' : ''}`} style={{ transitionDelay: `${index * 80}ms` }}>
      <span className="feat__num">{feature.number}</span>
      <div className="feat__body">
        <div>
          <h3 className="feat__title">{feature.title}</h3>
          <p className="feat__text">{feature.text}</p>
        </div>
        <div className="feat__visual" aria-hidden="true">
          <Visual />
        </div>
      </div>
    </div>
  );
}

export function FeaturesSection() {
  return (
    <section className="section" id="capacidades">
      <div className="wrap">
        <Reveal className="section-head">
          <span className="eyebrow">Capacidades</span>
          <h2 className="display">
            Todo lo que cambia en su cartelera.
            <br />
            <span className="muted">Nada que tengas que buscar a mano.</span>
          </h2>
        </Reveal>
        <div>
          {FEATURES.map((feature, i) => (
            <FeatureRow key={feature.number} feature={feature} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
