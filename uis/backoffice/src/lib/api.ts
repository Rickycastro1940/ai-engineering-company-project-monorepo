export type Location = {
  id: string;
  name: string;
  city: string;
  country: string;
  currency: "COP" | "USD";
  region: string;
};

export type LocationsOverview = {
  company: string;
  total_locations: number;
  countries: string[];
  currencies: Array<"COP" | "USD">;
  colombia_count: number;
  florida_count: number;
  source: string;
  locations: Location[];
};

export async function fetchLocationsOverview(): Promise<LocationsOverview> {
  const response = await fetch("/locations/overview");
  if (!response.ok) {
    throw new Error(`Failed to load locations overview (${response.status})`);
  }
  return response.json();
}
