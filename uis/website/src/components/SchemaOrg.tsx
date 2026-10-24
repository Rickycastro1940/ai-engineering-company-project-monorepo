import { brand } from "../content/brand";

const schema = {
  "@context": "https://schema.org",
  "@type": "Restaurant",
  name: brand.name,
  description: "Grilled food restaurant chain in Colombia and the United States",
  url: "https://brasaland.com",
  foundingDate: String(brand.founded),
  servesCuisine: "Grilled food, Colombian cuisine",
  priceRange: "$$",
  address: [
    {
      "@type": "PostalAddress",
      addressCountry: "CO",
      addressLocality: "Medellín",
      addressRegion: "Antioquia",
    },
    {
      "@type": "PostalAddress",
      addressCountry: "US",
      addressLocality: "Miami",
      addressRegion: "FL",
    },
  ],
  contactPoint: {
    "@type": "ContactPoint",
    telephone: "+57-4-123-4567",
    contactType: "customer service",
    availableLanguage: ["English", "Spanish"],
  },
  sameAs: [brand.social.instagram, brand.social.facebook],
};

export function SchemaOrg() {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
