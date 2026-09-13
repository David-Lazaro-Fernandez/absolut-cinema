'use client';

import { useEffect, useState } from 'react';
import { MAILTO, NAV_LINKS } from '@/lib/site';

export function Navigation() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  return (
    <header className={`nav ${scrolled || open ? 'nav--scrolled' : ''}`}>
      <nav className="nav__bar" aria-label="Principal">
        <a className="marca" href="#top">
          Matin<span>é</span>
        </a>

        <div className="nav__links">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href}>
              {link.name}
            </a>
          ))}
        </div>

        <div className="nav__cta">
          <a className="pill pill--primary pill--sm" href={MAILTO}>
            Solicitar acceso
          </a>
        </div>

        <button
          type="button"
          className={`nav__burger ${open ? 'is-open' : ''}`}
          aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span />
          <span />
        </button>
      </nav>

      <div className={`nav-overlay ${open ? 'is-open' : ''}`} aria-hidden={!open}>
        <div className="nav-overlay__links">
          {NAV_LINKS.map((link, i) => (
            <a
              key={link.href}
              href={link.href}
              style={{ transitionDelay: open ? `${i * 75}ms` : '0ms' }}
              onClick={() => setOpen(false)}
            >
              {link.name}
            </a>
          ))}
        </div>
        <div className="nav-overlay__actions">
          <a className="pill pill--primary" href={MAILTO} onClick={() => setOpen(false)}>
            Solicitar acceso
          </a>
        </div>
      </div>
    </header>
  );
}
