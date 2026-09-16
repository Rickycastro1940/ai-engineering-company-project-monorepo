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

export type PublicUser = {
  id: number;
  email: string;
  name: string | null;
  phone: string | null;
  address: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
};

export type ProfileUpdate = {
  name?: string;
  phone?: string;
  address?: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type AuthResponse = TokenResponse & {
  user: PublicUser;
};

const TOKEN_KEY = "auth_token";
const PUBLIC_AUTH_PATHS = new Set(["/auth/login", "/auth/register", "/auth/token"]);

export class ApiError extends Error {
  details: unknown;

  constructor(message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.details = details;
  }
}

export function getStoredToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

/** Drop the JWT. Redirect to `/login` unless already on a public auth page. */
export function clearSessionAndRedirectToLogin(): void {
  clearToken();
  const path = window.location.pathname;
  if (path === "/login" || path === "/register") {
    return;
  }
  window.location.replace("/login");
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers);
  const requestPath = path.split("?")[0];

  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const method = (options.method ?? "GET").toUpperCase();
  const isPublicAuthCall =
    PUBLIC_AUTH_PATHS.has(requestPath) || (requestPath === "/users" && method === "POST");

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (response.status === 401 && token && !isPublicAuthCall) {
    clearSessionAndRedirectToLogin();
  }

  if (!response.ok) {
    let message = "The request failed.";
    let details: unknown = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      details = body.detail ?? null;
      message = Array.isArray(details)
        ? "Please correct the highlighted fields."
        : typeof details === "string"
          ? details
          : message;
    } catch {
      message = (await response.text()) || message;
    }
    throw new ApiError(message, details);
  }

  if (response.status === 204) {
    return null as T;
  }
  return response.json() as Promise<T>;
}

export async function loginUser(email: string, password: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function createUserAccount(payload: {
  email: string;
  password: string;
  name?: string;
}): Promise<PublicUser> {
  const body: Record<string, string> = {
    email: payload.email,
    password: payload.password,
  };
  if (payload.name) {
    body.name = payload.name;
  }
  return apiRequest<PublicUser>("/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchCurrentUser(): Promise<PublicUser> {
  return apiRequest<PublicUser>("/auth/me");
}

export async function updateMyProfile(payload: ProfileUpdate): Promise<PublicUser> {
  return apiRequest<PublicUser>("/profiles/me", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function updateUser(
  userId: number,
  payload: { email?: string; password?: string; name?: string },
): Promise<PublicUser> {
  return apiRequest<PublicUser>(`/users/${encodeURIComponent(String(userId))}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export type InventoryProduct = {
  product_id: number;
  name: string;
  quantity: number;
  unit: string;
};

export async function fetchInventory(): Promise<InventoryProduct[]> {
  return apiRequest<InventoryProduct[]>("/inventory");
}

export async function fetchLocationsOverview(): Promise<LocationsOverview> {
  return apiRequest<LocationsOverview>("/locations/overview");
}
