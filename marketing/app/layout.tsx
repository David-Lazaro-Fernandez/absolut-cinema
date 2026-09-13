import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Matiné — Inteligencia competitiva de cartelera',
  description:
    'Matiné captura la cartelera de tu competencia varias veces al día y redacta solo los cambios que cruzan un umbral de negocio. Piloto activo en CDMX.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
