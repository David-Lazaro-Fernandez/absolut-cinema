import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import { DemoForm } from '@/components/demo-form';
import { FooterSection } from '@/components/footer-section';

export const metadata: Metadata = {
  title: 'Solicitar demo — Matiné',
  description: 'Pide una demo de Matiné: te mostramos el piloto con datos reales de cartelera.',
};

export default function RequestDemo() {
  return (
    <>
      <Navigation />
      <main>
        <DemoForm />
      </main>
      <FooterSection />
    </>
  );
}
