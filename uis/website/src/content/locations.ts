/** Marketing roster from the web-fundamentals BRIEFING (14 sites: Colombia 10 / Florida 4). */
export type MarketLocation = {
  id: string;
  name: string;
  city: string;
  country: "Colombia" | "United States";
  region: "Colombia" | "Florida";
  currency: "COP" | "USD";
};

export const locations: MarketLocation[] = [
  { id: "co-med-elpoblado", name: "Brasaland El Poblado", city: "Medellín", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-med-laureles", name: "Brasaland Laureles", city: "Medellín", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-med-envigado", name: "Brasaland Envigado", city: "Medellín", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-med-sabaneta", name: "Brasaland Sabaneta", city: "Medellín", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-bog-usaquen", name: "Brasaland Usaquén", city: "Bogotá", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-bog-chapinero", name: "Brasaland Chapinero", city: "Bogotá", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-bog-zonarosa", name: "Brasaland Zona Rosa", city: "Bogotá", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-cali-granada", name: "Brasaland Granada", city: "Cali", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-cali-ciudadjardin", name: "Brasaland Ciudad Jardín", city: "Cali", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "co-cali-unicentro", name: "Brasaland Unicentro", city: "Cali", country: "Colombia", region: "Colombia", currency: "COP" },
  { id: "us-mia-brickell", name: "Brasaland Brickell", city: "Miami", country: "United States", region: "Florida", currency: "USD" },
  { id: "us-mia-coralgables", name: "Brasaland Coral Gables", city: "Miami", country: "United States", region: "Florida", currency: "USD" },
  { id: "us-orl-downtown", name: "Brasaland Downtown", city: "Orlando", country: "United States", region: "Florida", currency: "USD" },
  { id: "us-orl-idrive", name: "Brasaland International Drive", city: "Orlando", country: "United States", region: "Florida", currency: "USD" },
];
