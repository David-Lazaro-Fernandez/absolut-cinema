import { CONTACT_EMAIL, MAILTO, NAV_LINKS } from '@/lib/site';

export function FooterSection() {
  return (
    <footer className="footer">
      <div className="wrap">
        <div className="footer__grid">
          <div className="footer__brand">
            <a className="marca" href="#top">
              Matin<span>é</span>
            </a>
            <p>
              Inteligencia competitiva de cartelera para exhibidores de cine. Piloto activo en México.
            </p>
          </div>
          <div>
            <h3>Producto</h3>
            <ul>
              {NAV_LINKS.map((link) => (
                <li key={link.href}>
                  <a href={link.href}>{link.name}</a>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3>Contacto</h3>
            <ul>
              <li>
                <a href={MAILTO}>{CONTACT_EMAIL}</a>
              </li>
              <li>
                <a href={MAILTO}>Solicitar acceso</a>
              </li>
            </ul>
          </div>
        </div>
        <div className="footer__bottom">
          <small>© {new Date().getFullYear()} Matiné.</small>
          <small>Piloto: Cinemex frente a Cinépolis · captura nacional</small>
        </div>
      </div>
    </footer>
  );
}
