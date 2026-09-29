import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import { Recommender } from '@/components/recommender';

export const metadata: Metadata = {
  title: '¿A dónde ir al cine? — Matiné',
  description:
    'Funciones cerca de ti en CDMX, Guadalajara y Monterrey que caben en tu presupuesto: boletos por persona y dulcería, con la cartelera y los precios de lista que captura Matiné.',
};

export default function ADondeIr() {
  return (
    <>
      <Navigation />
      <main>
        <Recommender />
      </main>
    </>
  );
}
