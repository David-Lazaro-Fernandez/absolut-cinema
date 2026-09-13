import { Reveal } from './reveal';

// Los seis principios de producto de ../AGENTS.md §2, reescritos para un lector externo.
const PRINCIPLES = [
  {
    title: 'Datos reales siempre',
    text:
      'Lo que no existe no se muestra con cifras. Sin datos de ejemplo ni aproximaciones: si un panel depende de historia que aún no hay, se declara pendiente y se dice qué lo desbloquea.',
  },
  {
    title: 'Umbral antes de afirmación',
    text:
      'Un hallazgo solo se redacta si la diferencia cruza un umbral definido de antemano. Si nada lo cruza, la capa lo dice. El ruido no se convierte en noticia.',
  },
  {
    title: 'Porcentajes, no absolutos',
    text:
      'Toda comparación entre cadenas es el porcentaje de la programación de cada una. Cadenas de distinto tamaño no se comparan en bruto: un absoluto engaña.',
  },
  {
    title: 'El día de hoy, ajustado',
    text:
      'Cualquier consulta que incluya el día en curso recorta desde el mismo momento para ambas cadenas, para que nadie gane la comparación por conservar más historial.',
  },
  {
    title: 'La semana es de jueves a miércoles',
    text:
      'Es lo que ambas cadenas publican completo. Las tendencias se cortan ahí, en la semana de cine, no en la del calendario.',
  },
  {
    title: 'En tu voz',
    text:
      'El tablero habla en primera persona de tu cadena: "nosotros" eres tú. Sin nombres internos ni jerga técnica en pantalla; cada etiqueta está escrita para quien decide.',
  },
];

export function PrinciplesSection() {
  return (
    <section className="section" id="metodologia">
      <div className="wrap">
        <Reveal className="section-head section-head--split">
          <div>
            <span className="eyebrow">Metodología</span>
            <h2 className="display" style={{ marginTop: 20 }}>
              Cómo pensamos los datos.
            </h2>
          </div>
          <p className="lead">
            Reglas que aplicamos a cada captura y cada hallazgo, sin excepción. Son la diferencia entre un reporte y
            una fuente en la que confías para decidir.
          </p>
        </Reveal>

        <div className="hgrid">
          {PRINCIPLES.map((p, i) => (
            <Reveal key={p.title} className="hgrid__cell" delay={i * 60}>
              <span className="hgrid__idx">{String(i + 1).padStart(2, '0')}</span>
              <h3 className="hgrid__title">{p.title}</h3>
              <p className="hgrid__text">{p.text}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
