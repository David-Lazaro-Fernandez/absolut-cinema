'use client';

import { useEffect, useState } from 'react';
import { MAILTO } from '@/lib/site';
import { Arrow } from './icons';
import { AsciiSphere } from './ascii-sphere';

const WORDS = ['programa', 'cancela', 'mueve', 'cobra'];

// Cada cifra sale de una constante real del repo (Makefile, scraper/plazas.py, analytics/labels.py, project.md).
const TICKER = [
  { value: '3×', label: 'capturas completas al día', meta: '07:30 · 13:30 · 20:30' },
  { value: '777', label: 'cines capturados en todo México', meta: '499 de Cinépolis · 278 de Cinemex' },
  { value: '3', label: 'plazas comparables', meta: 'CDMX · Guadalajara · Monterrey' },
  { value: '5', label: 'tipos de cambio detectados', meta: 'nueva · cancelada · movida · idioma o formato · ocupación' },
  { value: '6', label: 'franjas horarias', meta: 'de la matiné a después de las 9 P.M.' },
  { value: 'Jue–Mié', label: 'semana de cine', meta: 'lo que ambas cadenas publican completo' },
  { value: '1 h', label: 'entre lecturas de planos de asientos', meta: 'asistencia tras el inicio' },
  { value: '100 %', label: 'del crudo guardado', meta: 'cada captura se puede recalcular' },
];

export function HeroSection() {
  const [mounted, setMounted] = useState(false);
  const [wordIndex, setWordIndex] = useState(0);

  useEffect(() => {
    setMounted(true);
    const interval = setInterval(() => setWordIndex((i) => (i + 1) % WORDS.length), 2600);
    return () => clearInterval(interval);
  }, []);

  const inClass = mounted ? 'is-in' : '';

  return (
    <section className="hero" id="top">
      <div className="hero__grid" aria-hidden="true" />
      <div className="hero__sphere" aria-hidden="true">
        <AsciiSphere />
      </div>

      <div className="wrap hero__inner">
        <div className={`fade ${inClass}`}>
          <span className="eyebrow">Inteligencia competitiva de cartelera</span>
        </div>

        <h1 className={`hero__title fade ${inClass}`} style={{ transitionDelay: '100ms' }}>
          <span className="line">Lo que tu competencia</span>
          <span className="line">
            <span className="hero__word">
              <span key={wordIndex} className="hero__chars" aria-live="polite">
                {WORDS[wordIndex].split('').map((char, i) => (
                  <span key={`${wordIndex}-${i}`} className="char" style={{ animationDelay: `${i * 50}ms` }}>
                    {char}
                  </span>
                ))}
              </span>
            </span>
            .
          </span>
        </h1>

        <div className="hero__bottom">
          <p className={`hero__lead fade ${inClass}`} style={{ transitionDelay: '250ms' }}>
            Matiné captura la cartelera completa de tu competencia tres veces al día, la compara función por
            función y redacta solo los cambios que cruzan un umbral de negocio. Nada de revisar cartelera a mano.
          </p>
          <div className={`hero__actions fade ${inClass}`} style={{ transitionDelay: '350ms' }}>
            <a className="pill pill--primary" href={MAILTO}>
              Solicitar acceso
              <Arrow />
            </a>
            <a className="pill pill--ghost" href="#como-funciona">
              Cómo funciona
            </a>
          </div>
        </div>

        <div className={`hero__tag fade ${inClass}`} style={{ transitionDelay: '450ms' }}>
          <span className="dot" />
          Piloto activo: Cinemex frente a Cinépolis, captura nacional
        </div>
      </div>

      <div className={`ticker fade ${inClass}`} style={{ transitionDelay: '600ms' }} aria-hidden="true">
        <div className="ticker__track">
          {[0, 1].map((set) => (
            <div key={set} className="ticker__set">
              {TICKER.map((item) => (
                <div key={`${set}-${item.label}`} className="ticker__item">
                  <span className="ticker__value">{item.value}</span>
                  <span className="ticker__label">
                    {item.label}
                    <span className="ticker__meta">{item.meta}</span>
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
