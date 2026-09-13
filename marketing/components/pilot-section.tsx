'use client';

import { useEffect, useState } from 'react';
import { Reveal } from './reveal';

// Horarios del Makefile de la raíz (snapshot, seats, sync, daily, delivery). Hora de la Ciudad de México.
const SCHEDULE = [
  { time: '07:30', title: 'Cartelera completa', sub: 'Ambas cadenas, función por función' },
  { time: '13:30', title: 'Cartelera completa', sub: 'Segunda pasada del día' },
  { time: '20:30', title: 'Cartelera completa', sub: 'Cierre del día y funciones nocturnas' },
  { time: 'Cada hora', title: 'Planos de asientos', sub: 'Asistencia tras el inicio, en las plazas del piloto' },
  { time: ':22 y :52', title: 'Copia al archivo histórico', sub: 'Solo se agrega; nada se borra' },
  { time: '06:00', title: 'Salud, precios y dulcería', sub: 'Huecos de captura, boleto por formato, menú en sala' },
  { time: '15:00', title: 'Dulcería a domicilio', sub: 'Rappi y DiDi Food con las tiendas abiertas' },
];

export function PilotSection() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setActive((i) => (i + 1) % SCHEDULE.length), 2200);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className="section section--tint" id="piloto">
      <div className="wrap">
        <div className="pilot__grid">
          <Reveal>
            <span className="eyebrow">Piloto</span>
            <h2 className="display" style={{ margin: '20px 0 24px' }}>
              Un piloto real,
              <br />
              <span className="muted">no una maqueta.</span>
            </h2>
            <p className="lead" style={{ fontSize: '1.15rem', color: 'var(--gray)', maxWidth: '34rem' }}>
              Matiné corre hoy en producción sobre Cinemex frente a Cinépolis: captura la cartelera de los 777 cines de
              ambas cadenas en todo México, la compara dentro de cada plaza (Ciudad de México, Guadalajara y
              Monterrey) y guarda el histórico. Cada número de esta página sale de esa operación, no de una proyección.
            </p>
            <div className="pilot__stats">
              <div>
                <div className="stat__value">
                  <span>2</span>
                </div>
                <div className="stat__label">cadenas comparadas</div>
              </div>
              <div>
                <div className="stat__value">777</div>
                <div className="stat__label">cines capturados, tres veces al día</div>
              </div>
              <div>
                <div className="stat__value">3</div>
                <div className="stat__label">plazas comparables</div>
              </div>
            </div>
          </Reveal>

          <Reveal delay={150}>
            <div className="sched">
              <div className="sched__head">
                <span>Calendario diario</span>
                <span>Hora de la Ciudad de México</span>
              </div>
              {SCHEDULE.map((row, i) => (
                <div key={row.time + row.title} className={`sched__row ${active === i ? 'is-active' : ''}`}>
                  <div className="sched__left">
                    <span className="sched__dot" />
                    <div>
                      <div className="sched__title">{row.title}</div>
                      <div className="sched__sub">{row.sub}</div>
                    </div>
                  </div>
                  <span className="sched__time">{row.time}</span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
