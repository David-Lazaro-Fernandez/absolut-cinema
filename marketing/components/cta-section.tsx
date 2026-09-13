'use client';

import { CONTACT_EMAIL, MAILTO } from '@/lib/site';
import { Arrow } from './icons';
import { useReveal } from './reveal';

export function CtaSection() {
  const { ref, visible } = useReveal<HTMLDivElement>(0.2);

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`);
    e.currentTarget.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`);
  };

  return (
    <section className="section section--border" id="contacto">
      <div className="wrap">
        <div ref={ref} className={`cta reveal ${visible ? 'is-visible' : ''}`} onMouseMove={onMove}>
          <div className="cta__spot" aria-hidden="true" />
          <div className="cta__corner cta__corner--tr" aria-hidden="true" />
          <div className="cta__corner cta__corner--bl" aria-hidden="true" />

          <div className="cta__inner">
            <div>
              <h2 className="cta__title">
                ¿Tu cadena quiere ver esto
                <br />
                sobre su competencia?
              </h2>
              <p className="cta__lead">
                Escríbenos y te mostramos el piloto con datos reales antes de hablar de nada más.
              </p>
              <div className="cta__actions">
                <a className="pill pill--primary" href={MAILTO}>
                  Solicitar acceso
                  <Arrow />
                </a>
                <a className="pill pill--ghost" href="#piloto">
                  Ver el calendario de captura
                </a>
              </div>
              <p className="cta__note">Sin formulario ni demo grabada · {CONTACT_EMAIL}</p>
            </div>
            <div className="cta__mark" aria-hidden="true">
              Matin<span>é</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
