import { Navigation } from '@/components/navigation';
import { HeroSection } from '@/components/hero-section';
import { FeaturesSection } from '@/components/features-section';
import { HowItWorksSection } from '@/components/how-it-works-section';
import { AiSection } from '@/components/ai-section';
import { PilotSection } from '@/components/pilot-section';
import { PrinciplesSection } from '@/components/principles-section';
import { CtaSection } from '@/components/cta-section';
import { FooterSection } from '@/components/footer-section';

export default function Home() {
  return (
    <>
      <Navigation />
      <main>
        <HeroSection />
        <FeaturesSection />
        <HowItWorksSection />
        <AiSection />
        <PilotSection />
        <PrinciplesSection />
        <CtaSection />
      </main>
      <FooterSection />
    </>
  );
}
