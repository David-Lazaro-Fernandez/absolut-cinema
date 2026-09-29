'use client';

import { useEffect, useState } from 'react';
import * as check from '@/lib/demo';
import { CONTACT_EMAIL, EARLY_ACCESS } from '@/lib/site';
import { Arrow } from './icons';

const STEPS = ['Correo', 'Datos', 'Cadena', 'Operación'];

const ROLES = [
  'Dirección general',
  'Dirección comercial',
  'Revenue management o pricing',
  'Programación de cartelera',
  'Dulcería y alimentos',
  'Marketing',
  'Operaciones',
  'Finanzas',
  'Datos o TI',
  'Otro',
];
const EXHIBITOR_TYPES = ['Cadena nacional', 'Cadena regional', 'Cine independiente', 'Cineteca o espacio cultural', 'Otro'];
const COMPLEXES = ['1', '2 a 5', '6 a 20', '21 a 100', 'Más de 100'];
const INTERESTS = [
  'Precios de boletos por formato',
  'Programación y horarios',
  'Precios de dulcería',
  'Preventa y ocupación',
  'Todo lo anterior',
];
const SOURCES = ['Búsqueda en internet', 'LinkedIn', 'Recomendación', 'Evento de la industria', '¿A dónde ir?', 'Otro'];

type Data = Record<string, string>;

// Qué revisa cada paso antes de avanzar, en el orden de la pantalla: el foco va al primer campo con error.
const RULES: [string, (d: Data) => string][][] = [
  [['email', (d) => check.workEmail(d.email ?? '')]],
  [
    ['first_name', (d) => check.personName(d.first_name ?? '', 'nombre')],
    ['last_name', (d) => check.personName(d.last_name ?? '', 'apellido')],
    ['phone', (d) => check.phone(d.phone ?? '')],
    ['role', (d) => check.choice(d.role ?? '', 'Elige tu cargo.')],
  ],
  [
    ['company', (d) => check.text(d.company ?? '', 'Escribe el nombre de tu cadena.')],
    ['website', (d) => check.website(d.website ?? '')],
    ['type', (d) => check.choice(d.type ?? '', 'Elige el tipo de exhibidor.')],
  ],
  [
    ['complexes', (d) => check.choice(d.complexes ?? '', 'Elige cuántos complejos tienen.')],
    ['cities', (d) => check.text(d.cities ?? '', 'Escribe al menos una ciudad.')],
    ['interest', (d) => check.choice(d.interest ?? '', 'Elige qué quieres comparar.')],
  ],
];

// El orden y las etiquetas del correo que recibe Matiné.
const SUMMARY: [string, string][] = [
  ['access', 'Llegó desde'],
  ['email', 'Correo'],
  ['first_name', 'Nombre'],
  ['last_name', 'Apellido'],
  ['phone', 'Teléfono (+52)'],
  ['role', 'Cargo'],
  ['company', 'Cadena o exhibidor'],
  ['website', 'Sitio web'],
  ['type', 'Tipo de exhibidor'],
  ['complexes', 'Complejos'],
  ['cities', 'Ciudades'],
  ['interest', 'Qué quiere comparar'],
  ['source', 'Cómo llegó a Matiné'],
  ['notes', 'Comentarios'],
];

function Select({ options, placeholder, ...props }: { options: string[]; placeholder: string } & React.ComponentProps<'select'>) {
  return (
    <select {...props}>
      <option value="" disabled>
        {placeholder}
      </option>
      {options.map((o) => (
        <option key={o}>{o}</option>
      ))}
    </select>
  );
}

// Sin backend (design.md §6): el último paso abre el correo del visitante con la solicitud escrita.
export function DemoForm() {
  const [step, setStep] = useState(0);
  const [data, setData] = useState<Data>({});
  const [errors, setErrors] = useState<Data>({});
  const [sent, setSent] = useState(false);

  // Una llave desconocida se ignora: solo las puertas de EARLY_ACCESS cambian el asunto.
  useEffect(() => {
    const access = EARLY_ACCESS[new URLSearchParams(window.location.search).get('acceso') ?? ''];
    if (access) setData((d) => ({ ...d, access }));
  }, []);

  const field = (name: string) => ({
    name,
    id: `demo-${name}`,
    value: data[name] ?? '',
    'aria-invalid': errors[name] ? true : undefined,
    'aria-describedby': errors[name] ? `demo-${name}-error` : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setData((d) => ({ ...d, [name]: e.target.value }));
      if (errors[name]) setErrors(({ [name]: _, ...rest }) => rest);
    },
  });

  const error = (name: string) =>
    errors[name] ? (
      <span className="demo__error" id={`demo-${name}-error`}>
        {errors[name]}
      </span>
    ) : null;

  function next(e: React.SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const found = Object.fromEntries(RULES[step].map(([name, rule]) => [name, rule(data)]).filter(([, message]) => message));
    setErrors(found);
    const first = Object.keys(found)[0];
    if (first) return document.getElementById(`demo-${first}`)?.focus();
    if (step < STEPS.length - 1) return setStep(step + 1);
    const body = SUMMARY.filter(([k]) => data[k]?.trim())
      .map(([k, label]) => `${label}: ${data[k].trim()}`)
      .join('\n');
    const who = `${data.company?.trim()} (${data.first_name?.trim()} ${data.last_name?.trim()})`;
    const subject = `${data.access ?? 'Solicitar demo'} — ${who}`;
    const params = new URLSearchParams({ subject, body });
    window.location.href = `mailto:${CONTACT_EMAIL}?${params.toString().replace(/\+/g, '%20')}`;
    setSent(true);
  }

  return (
    <div className="demo">
      <section className="demo__intro">
        <span className="eyebrow eyebrow--red">Demo con datos reales</span>
        <h1 className="display demo__title">Estás a un paso de ver la cartelera de tu competencia</h1>
        <p className="demo__lead">
          Completa el formulario y te mostramos el piloto con la cartelera y los precios reales de tu plaza.
        </p>
        <ul className="demo__points">
          <li>
            <Arrow />
            Las dos cadenas más grandes del país y cine independiente
          </li>
          <li>
            <Arrow />
            Cartelera tres veces al día; boletos y dulcería a diario
          </li>
          <li>
            <Arrow />
            Captura en todo México desde septiembre de 2026
          </li>
        </ul>
      </section>

      <section className="demo__panel">
        <div className="demo__card">
          <ol className="demo__steps" aria-label="Pasos">
            {STEPS.map((label, i) => (
              <li key={label} className={i < step || sent ? 'is-done' : i === step ? 'is-on' : ''} aria-current={i === step && !sent ? 'step' : undefined}>
                <span className="demo__dot">{i + 1}</span>
                <span className="demo__step">{label}</span>
              </li>
            ))}
          </ol>

          {sent ? (
            <div className="demo__done" aria-live="polite">
              <h2 className="demo__h">Listo, se abrió tu correo</h2>
              <p className="demo__sub">
                La solicitud ya va escrita: solo envíala. Si no se abrió, escríbenos a{' '}
                <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
              </p>
              <button type="button" className="demo__back" onClick={() => { setSent(false); setStep(0); }}>
                ← Editar la solicitud
              </button>
            </div>
          ) : (
            <form key={step} className="demo__form" onSubmit={next} noValidate>
              {step === 0 && (
                <>
                  <div>
                    <h2 className="demo__h">¿Cuál es tu correo de trabajo?</h2>
                    <p className="demo__sub">Te escribimos ahí para agendar la demo.</p>
                  </div>
                  <label className="demo__field">
                    <span>Correo de trabajo</span>
                    <input type="email" autoComplete="email" required maxLength={200} placeholder="nombre@tucadena.com" {...field('email')} />
                    {error('email')}
                  </label>
                </>
              )}

              {step === 1 && (
                <>
                  <h2 className="demo__h">Cuéntanos sobre ti</h2>
                  <div className="demo__row">
                    <label className="demo__field">
                      <span>Nombre</span>
                      <input autoFocus autoComplete="given-name" required maxLength={80} placeholder="Ana" {...field('first_name')} />
                      {error('first_name')}
                    </label>
                    <label className="demo__field">
                      <span>Apellido</span>
                      <input autoComplete="family-name" required maxLength={80} placeholder="García" {...field('last_name')} />
                      {error('last_name')}
                    </label>
                  </div>
                  <label className="demo__field">
                    <span>Teléfono</span>
                    <span className="demo__phone">
                      <span className="demo__prefix">MX +52</span>
                      <input type="tel" autoComplete="tel-national" inputMode="tel" maxLength={20} placeholder="55 1234 5678" {...field('phone')} />
                    </span>
                    {error('phone')}
                  </label>
                  <label className="demo__field">
                    <span>Cargo</span>
                    <Select options={ROLES} placeholder="Selecciona tu cargo" required {...field('role')} />
                    {error('role')}
                  </label>
                </>
              )}

              {step === 2 && (
                <>
                  <h2 className="demo__h">Tu cadena</h2>
                  <label className="demo__field">
                    <span>Nombre de la cadena o exhibidor</span>
                    <input autoFocus autoComplete="organization" required maxLength={120} placeholder="Cines del Centro" {...field('company')} />
                    {error('company')}
                  </label>
                  <label className="demo__field">
                    <span>Sitio web</span>
                    <input type="text" inputMode="url" autoComplete="url" maxLength={200} placeholder="www.tucadena.com" {...field('website')} />
                    {error('website')}
                  </label>
                  <label className="demo__field">
                    <span>Tipo de exhibidor</span>
                    <Select options={EXHIBITOR_TYPES} placeholder="Selecciona un tipo" required {...field('type')} />
                    {error('type')}
                  </label>
                </>
              )}

              {step === 3 && (
                <>
                  <div>
                    <h2 className="demo__h">Tu operación</h2>
                    <p className="demo__sub">Con esto preparamos la demo con las plazas donde compites.</p>
                  </div>
                  <div className="demo__row">
                    <label className="demo__field">
                      <span>Complejos</span>
                      <Select autoFocus options={COMPLEXES} placeholder="¿Cuántos?" required {...field('complexes')} />
                      {error('complexes')}
                    </label>
                    <label className="demo__field">
                      <span>Ciudades</span>
                      <input required maxLength={200} placeholder="CDMX, Puebla…" {...field('cities')} />
                      {error('cities')}
                    </label>
                  </div>
                  <label className="demo__field">
                    <span>¿Qué quieres comparar?</span>
                    <Select options={INTERESTS} placeholder="Selecciona una opción" required {...field('interest')} />
                    {error('interest')}
                  </label>
                  <label className="demo__field">
                    <span>¿Cómo llegaste a Matiné?</span>
                    <Select options={SOURCES} placeholder="Selecciona una opción" {...field('source')} />
                  </label>
                  <label className="demo__field">
                    <span>Comentarios (opcional)</span>
                    <textarea rows={3} maxLength={2000} placeholder="Algo que quieras ver en la demo." {...field('notes')} />
                  </label>
                </>
              )}

              <button type="submit" className="pill pill--primary demo__submit">
                {step < STEPS.length - 1 ? 'Continuar' : 'Solicitar demo'}
                <Arrow />
              </button>
              {step > 0 && (
                <button type="button" className="demo__back" onClick={() => setStep(step - 1)}>
                  ← Volver
                </button>
              )}
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
