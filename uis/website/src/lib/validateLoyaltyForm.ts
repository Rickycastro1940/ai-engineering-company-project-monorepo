import { CITIES_BY_COUNTRY, ERRORS, LOCATIONS_BY_CITY, type Country } from "../content/loyaltySignup";

export type LoyaltyFormValues = {
  fullName: string;
  email: string;
  phone: string;
  country: string;
  city: string;
  favoriteLocation: string;
  dietary: string[];
  howFound: string;
  dateOfBirth: string;
  acceptTerms: boolean;
  receiveOffers: boolean;
};

export type FieldErrors = Partial<Record<keyof LoyaltyFormValues, string>>;

function ageAtLeast18(isoDate: string): boolean {
  if (!isoDate) return false;
  const born = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(born.getTime())) return false;
  const today = new Date();
  let age = today.getFullYear() - born.getFullYear();
  const monthDiff = today.getMonth() - born.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < born.getDate())) {
    age -= 1;
  }
  return age >= 18;
}

export function validateLoyaltyForm(values: LoyaltyFormValues): FieldErrors {
  const errors: FieldErrors = {};
  const nameParts = values.fullName.trim().split(/\s+/).filter(Boolean);
  if (nameParts.length < 2) {
    errors.fullName = ERRORS.fullName;
  }
  const email = values.email.trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = ERRORS.email;
  }
  const phone = values.phone.trim();
  if (!/^\+(57|1)\s?\d[\d\s-]{6,}$/.test(phone)) {
    errors.phone = ERRORS.phone;
  }
  if (values.country !== "Colombia" && values.country !== "United States") {
    errors.country = ERRORS.country;
  }
  if (!values.city.trim()) {
    errors.city = ERRORS.city;
  }
  if (!values.howFound.trim()) {
    errors.howFound = ERRORS.howFound;
  }
  if (!ageAtLeast18(values.dateOfBirth)) {
    errors.dateOfBirth = ERRORS.dateOfBirth;
  }
  if (!values.acceptTerms) {
    errors.acceptTerms = ERRORS.terms;
  }
  return errors;
}

export function emptyLoyaltyForm(): LoyaltyFormValues {
  return {
    fullName: "",
    email: "",
    phone: "",
    country: "",
    city: "",
    favoriteLocation: "",
    dietary: [],
    howFound: "",
    dateOfBirth: "",
    acceptTerms: false,
    receiveOffers: false,
  };
}

export function citiesFor(country: string): string[] {
  if (country === "Colombia" || country === "United States") {
    return CITIES_BY_COUNTRY[country as Country];
  }
  return [];
}

export function locationsFor(city: string): string[] {
  return LOCATIONS_BY_CITY[city] ?? [];
}
