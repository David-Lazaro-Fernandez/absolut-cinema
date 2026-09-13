'use client';

import { useEffect, useState } from 'react';
import { Reveal } from './reveal';

const STEP_MS = 5000;

const STEPS = [
  {
    roman: 'I',
    title: 'Lo que importa hoy',
    text:
      'Hasta tres hallazgos redactados como decisión, con sus números de soporte al lado. Si ningún cambio cruza su umbral, la capa lo dice y no inventa un hallazgo para llenar espacio.',
    window: 'Cartelera · Capa 1',
  },
  {
    roman: 'II',
    title: 'Evidencia por pregunta',
    text:
      'Cada hallazgo se sostiene con la pregunta de negocio que responde, la conclusión y el gráfico que la prueba, más una guía de cómo leerlo. Nunca tienes que confiar a ciegas.',
    window: 'Cartelera · Capa 2',
  },
  {
    roman: 'III',
    title: 'Detalle y archivo',
    text:
      'Todo lo demás queda disponible y colapsado: el histórico de cada función, cine y producto, para auditar un hallazgo o construir tu propio análisis encima.',
    window: 'Cartelera · Capa 3',
  },
];

function MockHallazgo() {
  return (
    <div>
      <span className="mk__tag mk__tag--red">CAPA 1</span>
      <div className="mk__card mk__card--accent">
        <span className="mk__line" style={{ width: '74%' }} />
        <span className="mk__line mk__line--thin" style={{ width: '56%' }} />
        <span className="mk__chip">Decisión</span>
        <div className="mk__kv">
          {[
            [58, 'red'],
            [40, 'ink'],
            [66, 'red'],
            [34, 'ink'],
          ].map(([w, tone], i) => (
            <div key={i}>
              <span className="mk__line mk__line--thin" style={{ width: '62%' }} />
              <span className={`mk__line ${tone === 'red' ? 'mk__line--red' : ''}`} style={{ width: `${w}%`, height: 12 }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MockEvidencia() {
  const groups: [number, number][] = [
    [70, 50],
    [42, 62],
    [56, 58],
    [82, 66],
    [92, 72],
    [60, 48],
  ];
  return (
    <div>
      <span className="mk__tag">CAPA 2</span>
      <div className="mk__card">
        <span className="mk__line" style={{ width: '82%' }} />
        <div className="mk__conclusion">
          <span className="mk__line" style={{ width: '92%' }} />
          <span className="mk__line mk__line--thin" style={{ width: '58%' }} />
        </div>
        <div className="mk__legend">
          <span>
            <i className="mk__sw" />
            Tu cadena
          </span>
          <span>
            <i className="mk__sw mk__sw--them" />
            Competencia
          </span>
        </div>
        <div className="mk__bars">
          {groups.map(([a, b], i) => (
            <div key={i} className="mk__group">
              <i style={{ height: `${a}%` }} />
              <i className="them" style={{ height: `${b}%` }} />
            </div>
          ))}
        </div>
        <div className="mk__foot">
          Cómo leerla <b>▾</b>
        </div>
      </div>
    </div>
  );
}

function MockApendice() {
  return (
    <div>
      <span className="mk__tag">CAPA 3</span>
      {[
        [34, 44],
        [42, 36],
        [28, 48],
      ].map(([a, b], i) => (
        <div key={i} className="mk__row">
          <span className="mk__chev">▸</span>
          <span className="mk__line" style={{ width: `${a}%` }} />
          <span className="mk__line mk__line--thin" style={{ width: `${b}%` }} />
        </div>
      ))}
      <div className="mk__dark">
        <span className="mk__line mk__line--paper" style={{ width: '58%' }} />
        <span className="mk__line mk__line--thin mk__line--paper" style={{ width: '86%' }} />
      </div>
    </div>
  );
}

const MOCKS = [MockHallazgo, MockEvidencia, MockApendice];

export function HowItWorksSection() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setActive((i) => (i + 1) % STEPS.length), STEP_MS);
    return () => clearInterval(interval);
  }, [active]);

  const Mock = MOCKS[active];

  return (
    <section className="section section--dark how" id="como-funciona">
      <div className="how__pattern" aria-hidden="true" />
      <div className="wrap">
        <Reveal className="section-head">
          <span className="eyebrow">Cómo funciona</span>
          <h2 className="display">
            Tres capas.
            <br />
            <span className="muted">De la decisión al detalle.</span>
          </h2>
          <p className="lead">
            No es un tablero con veinte gráficas. Es la misma estructura editorial que usa el producto por dentro: lo
            urgente arriba, la prueba después, el archivo completo al final.
          </p>
        </Reveal>

        <div className="how__grid">
          <div className="how__steps">
            {STEPS.map((step, i) => (
              <button
                key={step.roman}
                type="button"
                className={`how__step ${active === i ? 'is-active' : ''}`}
                onClick={() => setActive(i)}
                aria-pressed={active === i}
              >
                <span className="how__roman">{step.roman}</span>
                <span style={{ flex: 1 }}>
                  <span className="how__title" style={{ display: 'block' }}>
                    {step.title}
                  </span>
                  <span className="how__text" style={{ display: 'block' }}>
                    {step.text}
                  </span>
                  {active === i && (
                    <span className="how__progress" style={{ display: 'block' }}>
                      <i key={active} />
                    </span>
                  )}
                </span>
              </button>
            ))}
          </div>

          <div className="how__panel">
            <div className="win">
              <div className="win__bar">
                <span className="win__dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="win__name">{STEPS[active].window}</span>
              </div>
              <div className="win__body" key={active}>
                <Mock />
              </div>
              <div className="win__foot">Estructura ilustrativa del tablero; sin datos de ningún cliente.</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
