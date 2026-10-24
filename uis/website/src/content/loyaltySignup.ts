/** Brasa Points signup options from the web-fundamentals BRIEFING (Camila Ospina). */

export const COUNTRIES = ["Colombia", "United States"] as const;

export type Country = (typeof COUNTRIES)[number];

export const CITIES_BY_COUNTRY: Record<Country, string[]> = {
  Colombia: ["Medellín", "Bogotá", "Cali"],
  "United States": ["Miami", "Orlando"],
};

export const LOCATIONS_BY_CITY: Record<string, string[]> = {
  Medellín: [
    "Brasaland El Poblado",
    "Brasaland Laureles",
    "Brasaland Envigado",
    "Brasaland Sabaneta",
  ],
  Bogotá: ["Brasaland Usaquén", "Brasaland Chapinero", "Brasaland Zona Rosa"],
  Cali: ["Brasaland Granada", "Brasaland Ciudad Jardín", "Brasaland Unicentro"],
  Miami: ["Brasaland Brickell", "Brasaland Coral Gables"],
  Orlando: ["Brasaland Downtown", "Brasaland International Drive"],
};

export const DIETARY_OPTIONS = [
  "No restrictions",
  "Vegetarian",
  "Gluten-free",
  "Other",
] as const;

export const HOW_FOUND_OPTIONS = [
  "Social media",
  "Recommendation",
  "Walked by",
  "Internet search",
  "Other",
] as const;

export const ERRORS = {
  fullName: "Enter your full name (first and last name)",
  email: "Enter a valid email (example: name@email.com)",
  phone: "Phone must include country code (example: +57 300 123 4567 or +1 305 123 4567)",
  country: "Select your country",
  city: "Select your city",
  howFound: "Tell us how you found Brasaland",
  dateOfBirth: "You must be 18 or older to register for Brasa Points",
  terms: "You must accept the Brasa Points program terms to continue",
} as const;

export const SUCCESS_TITLE = "Welcome to Brasa Points!";
export const SUCCESS_BODY =
  "Your registration was successful. You will receive a confirmation email in the next few minutes with your account details and how to start earning points. You can now enjoy your benefits at any of our 14 locations!";

export const ORDERING_NOTE =
  "Want to place an order? Call your favorite location or visit us directly. Online ordering coming soon!";
