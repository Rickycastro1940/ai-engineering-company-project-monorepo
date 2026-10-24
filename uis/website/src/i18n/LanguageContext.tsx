import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "es";

const copy = {
  en: {
    nav: { home: "Home", locations: "Locations", menu: "Menu", points: "Brasa Points", contact: "Contact", join: "Join Brasa Points" },
    hero: {
      kicker: "Brasaland · Since 2008",
      headline: "The taste of the grill, in every bite",
      sub: "Since 2008 serving the best grilled meats in Colombia and the United States. 14 locations, one passion for quality and flavor.",
      locations: "Explore 14 locations",
    },
    story: {
      eyebrow: "Our story",
      title: "From one Medellín kitchen to two countries",
      body: "Founded in Medellín in 2008, Brasaland began as a family dream: sharing the authentic taste of grilled meat with consistent quality and warm service. Today we are 14 restaurants in two countries, but we maintain the same recipe for success: fresh products, traditional techniques, and passion for every dish we serve.",
      caption: "Fresh product, traditional techniques, and a kitchen that moves fast.",
      alt: "Stylized charcoal grill representing Brasaland kitchens",
    },
    pillars: {
      eyebrow: "What we stand for",
      title: "Three commitments in every kitchen",
      lead: "From a single family grill in Medellín to 14 company-owned restaurants, Brasaland still runs on the same three promises.",
      items: [
        { title: "Consistent Quality", body: "Same recipes and standards in all locations. Fresh ingredients selected daily." },
        { title: "Warm Experience", body: "Friendly and attentive service. Family atmosphere on every visit." },
        { title: "Speed", body: "Your food ready in minutes — without sacrificing flavor or quality." },
      ],
    },
    markets: {
      eyebrow: "Two countries · COP & USD",
      title: "14 locations. One standard.",
      lead: "About 115 people run Brasaland across Colombia and Florida — one chain, two markets, one plate that should taste the same.",
      colombiaName: "Colombia",
      colombiaHub: "10 restaurants in Medellín, Bogotá and Cali",
      colombiaCopy: "Hours: Mon–Sun 11:00 AM – 10:00 PM. Headquarters in Medellín keeps the original grill standard.",
      floridaName: "United States (Florida)",
      floridaHub: "4 restaurants in Miami and Orlando",
      floridaCopy: "Hours: Mon–Sun 11:00 AM – 10:00 PM. Miami office coordinates Florida locations — same recipes, second market.",
      roster: "See the full location roster →",
    },
    loyalty: {
      eyebrow: "Loyalty",
      title: "Brasa Points",
      lead: "Accumulate 1 point for every $10,000 COP or $5 USD. Redeem for discounts and free dishes. Exclusive member offers. 100% digital registration — no more paper cards.",
      how: "How it works",
      aside: "Earn points with every visit",
      bullets: [
        "1 point for every $10,000 COP or $5 USD",
        "Redeem for discounts and free dishes",
        "Exclusive offers for members",
        "100% digital registration — no more paper cards",
      ],
    },
    contact: {
      eyebrow: "Contact",
      title: "Talk to Brasaland",
      email: "Email",
      colombia: "Colombia",
      florida: "Florida",
    },
    footer: { rights: "© 2025 Brasaland. All rights reserved.", join: "Join" },
    ordering: "Want to place an order? Call your favorite location or visit us directly. Online ordering coming soon!",
    join: {
      eyebrow: "Brasa Points",
      title: "Join the loyalty programme",
      lead: "Register for digital Brasa Points. Earn 1 point for every $10,000 COP or $5 USD and redeem at any of our 14 locations. Guests must be 18 or older.",
      details: "Your details",
      visit: "Where you visit",
      prefs: "Preferences",
      fullName: "Full name",
      email: "Email",
      phone: "Phone",
      dob: "Date of birth",
      country: "Country",
      city: "City",
      favorite: "Favorite Brasaland location",
      optional: "(optional)",
      dietary: "Dietary preferences",
      howFound: "How did you find us?",
      terms: "I accept the Brasa Points program terms",
      offers: "I want to receive offers via email",
      submit: "Join Brasa Points",
      clear: "Clear form",
      another: "Register another guest",
      find: "Find a location",
      selectCountry: "Select your country",
      selectCity: "Select your city",
      selectLocation: "Select a location",
      selectHow: "Select an option",
      successTitle: "Welcome to Brasa Points!",
      successBody:
        "Your registration was successful. You will receive a confirmation email in the next few minutes with your account details and how to start earning points. You can now enjoy your benefits at any of our 14 locations!",
    },
    errors: {
      fullName: "Enter your full name (first and last name)",
      email: "Enter a valid email (example: name@email.com)",
      phone: "Phone must include country code (example: +57 300 123 4567 or +1 305 123 4567)",
      country: "Select your country",
      city: "Select your city",
      howFound: "Tell us how you found Brasaland",
      dateOfBirth: "You must be 18 or older to register for Brasa Points",
      terms: "You must accept the Brasa Points program terms to continue",
    },
    pointsPage: {
      eyebrow: "Loyalty programme",
      howTitle: "Earn points with every visit",
      step: "Step",
      steps: [
        { title: "Earn on every visit", body: "Accumulate 1 point for every $10,000 COP or $5 USD spent at any Brasaland location." },
        { title: "Redeem rewards", body: "Use points for discounts and free dishes. Members also get exclusive offers." },
        { title: "Register once, digital", body: "Sign up online — no more lost paper stamp cards. Guests must be 18 or older." },
      ],
      formLink: "Open the registration form →",
      locationsLink: "Browse locations →",
    },
    locationsPage: {
      title: "14 company-owned locations",
      lead: "Same recipes in every kitchen. Menus list prices in COP and USD depending on the market — Colombia kitchens settle in COP; Florida kitchens in USD.",
      restaurants: "restaurants",
      colombia: "Colombia · COP",
      florida: "Florida · USD",
      hq: "HQ",
      office: "Office",
    },
    options: {
      countries: { Colombia: "Colombia", "United States": "United States" },
      dietary: {
        "No restrictions": "No restrictions",
        Vegetarian: "Vegetarian",
        "Gluten-free": "Gluten-free",
        Other: "Other",
      },
      howFound: {
        "Social media": "Social media",
        Recommendation: "Recommendation",
        "Walked by": "Walked by",
        "Internet search": "Internet search",
        Other: "Other",
      },
    },
    langLabel: "Language",
  },
  es: {
    nav: { home: "Inicio", locations: "Sedes", menu: "Menú", points: "Brasa Points", contact: "Contacto", join: "Únete a Brasa Points" },
    hero: {
      kicker: "Brasaland · Desde 2008",
      headline: "El sabor de la parrilla, en cada bocado",
      sub: "Desde 2008 sirviendo las mejores carnes a la parrilla en Colombia y Estados Unidos. 14 sedes, una pasión por la calidad y el sabor.",
      locations: "Explorar 14 sedes",
    },
    story: {
      eyebrow: "Nuestra historia",
      title: "De una cocina en Medellín a dos países",
      body: "Fundado en Medellín en 2008, Brasaland empezó como un sueño familiar: compartir el sabor auténtico de la carne a la parrilla con calidad constante y servicio cálido. Hoy somos 14 restaurantes en dos países, con la misma receta de éxito: producto fresco, técnica tradicional y pasión por cada plato.",
      caption: "Producto fresco, técnicas tradicionales y una cocina que se mueve rápido.",
      alt: "Parrilla de carbón estilizada que representa las cocinas Brasaland",
    },
    pillars: {
      eyebrow: "Lo que nos define",
      title: "Tres compromisos en cada cocina",
      lead: "De una parrilla familiar en Medellín a 14 restaurantes propios, Brasaland sigue las mismas tres promesas.",
      items: [
        { title: "Calidad constante", body: "Las mismas recetas y estándares en todas las sedes. Ingredientes frescos cada día." },
        { title: "Experiencia cálida", body: "Servicio atento y cercano. Ambiente familiar en cada visita." },
        { title: "Rapidez", body: "Tu comida lista en minutos, sin sacrificar sabor ni calidad." },
      ],
    },
    markets: {
      eyebrow: "Dos países · COP y USD",
      title: "14 sedes. Un solo estándar.",
      lead: "Cerca de 115 personas operan Brasaland en Colombia y Florida: una cadena, dos mercados, un plato que debe saber igual.",
      colombiaName: "Colombia",
      colombiaHub: "10 restaurantes en Medellín, Bogotá y Cali",
      colombiaCopy: "Horario: lun–dom 11:00 a. m. – 10:00 p. m. La sede central en Medellín cuida el estándar original.",
      floridaName: "Estados Unidos (Florida)",
      floridaHub: "4 restaurantes en Miami y Orlando",
      floridaCopy: "Horario: lun–dom 11:00 a. m. – 10:00 p. m. La oficina de Miami coordina Florida con las mismas recetas.",
      roster: "Ver todas las sedes →",
    },
    loyalty: {
      eyebrow: "Fidelización",
      title: "Brasa Points",
      lead: "Acumula 1 punto por cada $10.000 COP o $5 USD. Canjea descuentos y platos gratis. Ofertas exclusivas. Registro 100% digital, sin tarjetas de papel.",
      how: "Cómo funciona",
      aside: "Gana puntos en cada visita",
      bullets: [
        "1 punto por cada $10.000 COP o $5 USD",
        "Canjea descuentos y platos gratis",
        "Ofertas exclusivas para miembros",
        "Registro 100% digital, sin tarjetas de papel",
      ],
    },
    contact: {
      eyebrow: "Contacto",
      title: "Habla con Brasaland",
      email: "Correo",
      colombia: "Colombia",
      florida: "Florida",
    },
    footer: { rights: "© 2025 Brasaland. Todos los derechos reservados.", join: "Únete" },
    ordering: "¿Quieres hacer un pedido? Llama a tu sede favorita o visítanos. Pedidos en línea, muy pronto.",
    join: {
      eyebrow: "Brasa Points",
      title: "Únete al programa de fidelización",
      lead: "Regístrate en Brasa Points digital. Gana 1 punto por cada $10.000 COP o $5 USD y canjéalos en cualquiera de las 14 sedes. Solo mayores de 18 años.",
      details: "Tus datos",
      visit: "Dónde nos visitas",
      prefs: "Preferencias",
      fullName: "Nombre completo",
      email: "Correo",
      phone: "Teléfono",
      dob: "Fecha de nacimiento",
      country: "País",
      city: "Ciudad",
      favorite: "Sede Brasaland favorita",
      optional: "(opcional)",
      dietary: "Preferencias alimentarias",
      howFound: "¿Cómo nos conociste?",
      terms: "Acepto los términos del programa Brasa Points",
      offers: "Quiero recibir ofertas por correo",
      submit: "Unirme a Brasa Points",
      clear: "Limpiar formulario",
      another: "Registrar a otra persona",
      find: "Buscar una sede",
      selectCountry: "Selecciona tu país",
      selectCity: "Selecciona tu ciudad",
      selectLocation: "Selecciona una sede",
      selectHow: "Selecciona una opción",
      successTitle: "¡Bienvenido a Brasa Points!",
      successBody:
        "Tu registro fue exitoso. Recibirás un correo de confirmación en los próximos minutos con los datos de tu cuenta y cómo empezar a ganar puntos. Ya puedes disfrutar tus beneficios en cualquiera de nuestras 14 sedes.",
    },
    errors: {
      fullName: "Escribe tu nombre completo (nombre y apellido)",
      email: "Escribe un correo válido (ejemplo: nombre@correo.com)",
      phone: "El teléfono debe incluir el código de país (ejemplo: +57 300 123 4567 o +1 305 123 4567)",
      country: "Selecciona tu país",
      city: "Selecciona tu ciudad",
      howFound: "Cuéntanos cómo conociste Brasaland",
      dateOfBirth: "Debes tener 18 años o más para registrarte en Brasa Points",
      terms: "Debes aceptar los términos de Brasa Points para continuar",
    },
    pointsPage: {
      eyebrow: "Programa de fidelización",
      howTitle: "Gana puntos en cada visita",
      step: "Paso",
      steps: [
        { title: "Gana en cada visita", body: "Acumula 1 punto por cada $10.000 COP o $5 USD en cualquier sede Brasaland." },
        { title: "Canjea premios", body: "Usa tus puntos en descuentos y platos gratis. Los miembros reciben ofertas exclusivas." },
        { title: "Un solo registro digital", body: "Inscríbete en línea, sin tarjetas de papel que se pierden. Solo mayores de 18 años." },
      ],
      formLink: "Abrir el formulario →",
      locationsLink: "Ver sedes →",
    },
    locationsPage: {
      title: "14 sedes propias",
      lead: "Las mismas recetas en cada cocina. Los precios se muestran en COP o USD según el mercado.",
      restaurants: "restaurantes",
      colombia: "Colombia · COP",
      florida: "Florida · USD",
      hq: "Sede central",
      office: "Oficina",
    },
    options: {
      countries: { Colombia: "Colombia", "United States": "Estados Unidos" },
      dietary: {
        "No restrictions": "Sin restricciones",
        Vegetarian: "Vegetariano",
        "Gluten-free": "Sin gluten",
        Other: "Otro",
      },
      howFound: {
        "Social media": "Redes sociales",
        Recommendation: "Recomendación",
        "Walked by": "Pasé por el local",
        "Internet search": "Búsqueda en internet",
        Other: "Otro",
      },
    },
    langLabel: "Idioma",
  },
} as const;

type Copy = (typeof copy)["en"];

type Ctx = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Copy;
};

const LanguageContext = createContext<Ctx | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    if (typeof window === "undefined") return "en";
    return window.localStorage.getItem("brasaland-lang") === "es" ? "es" : "en";
  });

  useEffect(() => {
    document.documentElement.lang = lang;
    window.localStorage.setItem("brasaland-lang", lang);
  }, [lang]);

  const value = useMemo<Ctx>(
    () => ({
      lang,
      setLang: setLangState,
      t: copy[lang] as Copy,
    }),
    [lang],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useI18n must be used inside LanguageProvider");
  }
  return ctx;
}
