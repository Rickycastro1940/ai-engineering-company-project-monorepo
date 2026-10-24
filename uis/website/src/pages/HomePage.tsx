import { BrandPillars } from "../components/BrandPillars";
import { ContactBlock } from "../components/ContactBlock";
import { Hero } from "../components/Hero";
import { LoyaltyTeaser } from "../components/LoyaltyTeaser";
import { Markets } from "../components/Markets";
import { OurStory } from "../components/OurStory";
import { SchemaOrg } from "../components/SchemaOrg";
import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";

export function HomePage() {
  return (
    <>
      <SchemaOrg />
      <SiteHeader />
      <main id="main-content">
        <Hero />
        <OurStory />
        <BrandPillars />
        <Markets />
        <LoyaltyTeaser />
        <ContactBlock />
      </main>
      <SiteFooter />
    </>
  );
}
