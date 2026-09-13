import { CONTACT_EMAIL } from '@/lib/site';
import { Arrow } from './icons';
import { Reveal } from './reveal';

// Fake door test (design.md §3): nada de esto existe hoy. Cada puerta lleva su propio asunto en el mailto para
// contar el interés por separado. El diseño del resumen narrado vive en ../project.md § "Paso 2".
const door = (subject: string) => `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}`;

const DOORS = [
  {
    status: 'Próximamente',
    title: 'Redacta, nunca calcula',
    text:
      'El modelo recibe solo los hallazgos que ya cruzaron su umbral y devuelve un resumen ejecutivo en prosa. Cada cifra del texto se valida contra los datos de entrada; si no existe, el texto se descarta y queda la plantilla.',
    cta: 'Quiero el resumen narrado',
    subject: 'Acceso anticipado: Resumen general narrado con IA',
  },
  {
    status: 'Próximamente',
    title: 'Tu modelo, tu clave',
    text:
      'Eliges el proveedor (Anthropic, OpenAI, Google o Bedrock desde tu propia cuenta de AWS). La clave se guarda cifrada, solo se muestran sus últimos cuatro caracteres, se puede revocar en un clic y cada uso queda auditado.',
    cta: 'Me interesa usar mi propia clave',
    subject: 'Acceso anticipado: IA con la clave de mi cadena',
  },
  {
    status: 'En evaluación',
    title: 'Un agente que te avisa',
    text:
      'Cuando la competencia cancela, mueve o abre funciones en tu plaza, un agente lo detecta en la siguiente captura y te lo escribe con la evidencia adjunta, por correo o por WhatsApp. Tú fijas el umbral que amerita aviso.',
    cta: 'Avísenme cuando exista',
    subject: 'Acceso anticipado: agente de alertas de cartelera',
  },
];

function MockNarrative() {
  const lines: [number, number[]][] = [
    [96, [22, 61]],
    [88, [40]],
    [92, [8, 74]],
    [70, []],
  ];
  return (
    <div className="mk__prose">
      <span className="mk__tag mk__tag--red">Resumen general</span>
      <span className="mk__line" style={{ width: '64%', height: 14 }} />
      {lines.map(([w, marks], i) => (
        <span key={i} className="mk__prose-line" style={{ width: `${w}%` }}>
          {marks.map((left) => (
            <i key={left} className="mk__num" style={{ left: `${left}%` }} />
          ))}
        </span>
      ))}
      <div className="mk__prose-foot">
        <span className="mk__check" />
        Cada cifra del texto existe en los datos. Las que no, no se publican.
      </div>
    </div>
  );
}

export function AiSection() {
  return (
    <section className="section section--border" id="ia">
      <div className="wrap">
        <Reveal className="section-head">
          <span className="eyebrow">Inteligencia artificial · acceso anticipado</span>
          <h2 className="display">
            Un analista que redacta el resumen.
            <br />
            <span className="muted">Con tus reglas y con tu clave.</span>
          </h2>
          <p className="lead">
            Hoy los hallazgos se redactan con plantillas deterministas. Lo siguiente es una capa narrativa opcional que
            escribe el resumen ejecutivo en prosa después de cada captura, con el modelo que tu cadena elija. Estamos
            abriéndola primero a quienes la pidan.
          </p>
        </Reveal>

        <div className="ai__grid">
          <div className="ai__cards">
            {DOORS.map((d, i) => (
              <Reveal key={d.title} className="ai__card" delay={i * 80}>
                <span className="ai__status">{d.status}</span>
                <h3 className="ai__title">{d.title}</h3>
                <p className="ai__text">{d.text}</p>
                <a className="ai__more" href={door(d.subject)}>
                  {d.cta}
                  <Arrow />
                </a>
              </Reveal>
            ))}
          </div>

          <Reveal delay={200} className="ai__panel">
            <div className="win">
              <div className="win__bar">
                <span className="win__dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="win__name">Cartelera · Resumen general · generado tras la captura de las 13:30</span>
              </div>
              <div className="win__body">
                <MockNarrative />
              </div>
              <div className="win__foot">Maqueta de lo que se está construyendo; no es una salida real del modelo.</div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
