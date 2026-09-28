// Reglas del formulario de /request-demo/. Cada función devuelve el mensaje para el visitante, o '' si el valor sirve.

// Correos personales: la demo es para cadenas, así que pide el de trabajo. Los proveedores con varios dominios por país
// (hotmail.es, yahoo.com.mx, live.com.mx) van por nombre; los demás, por dominio exacto.
const PERSONAL_PROVIDER = /^(gmail|googlemail|hotmail|outlook|live|msn|yahoo|ymail|aol|gmx|yandex)\.[a-z.]+$/;
const PERSONAL_DOMAINS = new Set([
  'icloud.com',
  'me.com',
  'mac.com',
  'proton.me',
  'protonmail.com',
  'pm.me',
  'mail.com',
  'zoho.com',
  'tutanota.com',
  'prodigy.net.mx',
]);

const EMAIL = /^[^\s@]+@([a-z0-9-]+\.)+[a-z]{2,}$/i;
const NAME = /^\p{L}[\p{L}\s'’.-]*$/u;
const DOMAIN = /^([a-z0-9-]+\.)+[a-z]{2,}(\/\S*)?$/i;

export function workEmail(value: string) {
  const email = value.trim().toLowerCase();
  if (!email) return 'Escribe tu correo de trabajo.';
  if (!EMAIL.test(email)) return 'Revisa el correo: debe verse como nombre@tucadena.com.';
  const domain = email.split('@')[1];
  if (PERSONAL_PROVIDER.test(domain) || PERSONAL_DOMAINS.has(domain)) {
    return 'Usa el correo de tu empresa, no uno personal.';
  }
  return '';
}

export function personName(value: string, label: string) {
  const name = value.trim();
  if (!name) return `Escribe tu ${label}.`;
  if (name.length < 2 || !NAME.test(name)) return `Revisa tu ${label}: solo letras, espacios y guiones.`;
  return '';
}

/** Opcional. Un número de México tiene 10 dígitos después del +52. */
export function phone(value: string) {
  const digits = value.replace(/[\s().-]/g, '');
  if (!digits) return '';
  if (!/^\d{10}$/.test(digits)) return 'Escribe los 10 dígitos del teléfono, sin el +52.';
  return '';
}

/** Opcional. Acepta el dominio con o sin https:// y www. */
export function website(value: string) {
  const site = value.trim().replace(/^https?:\/\//i, '');
  if (!site) return '';
  if (!DOMAIN.test(site)) return 'Revisa el sitio: debe verse como www.tucadena.com.';
  return '';
}

export function text(value: string, message: string, min = 2) {
  const t = value.trim();
  if (t.length < min || !/\p{L}/u.test(t)) return message;
  return '';
}

export function choice(value: string, message: string) {
  return value ? '' : message;
}
