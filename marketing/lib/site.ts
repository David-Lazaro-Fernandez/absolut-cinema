export const CONTACT_EMAIL = 'hola@matine.mx'; // TODO: confirmar bandeja real antes de publicar
export const MAILTO = `mailto:${CONTACT_EMAIL}`;
export const DEMO_URL = '/request-demo/';

// Puertas falsas de la IA (design.md §3): cada una llega a /request-demo/?acceso=llave y su asunto va en el correo.
export const EARLY_ACCESS: Record<string, string> = {
  resumen: 'Acceso anticipado: Resumen general narrado con IA',
  clave: 'Acceso anticipado: IA con la clave de mi cadena',
  alertas: 'Acceso anticipado: agente de alertas de cartelera',
};

// Anclas con la ruta completa ("/#…") para que funcionen también desde /a-donde-ir/.
export const NAV_LINKS = [
  { name: 'Capacidades', href: '/#capacidades' },
  { name: 'Cómo funciona', href: '/#como-funciona' },
  { name: 'IA', href: '/#ia' },
  { name: 'Piloto', href: '/#piloto' },
  { name: 'Metodología', href: '/#metodologia' },
  { name: '¿A dónde ir?', href: '/a-donde-ir/' },
];
