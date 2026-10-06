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
  status: number | null;

  constructor(message: string, details: unknown = null, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.details = details;
    this.status = status;
  }
}

export const SUPPORT_PROMPT =
  "If this continues, contact Brasaland Digital at Medellín headquarters.";

function looksTechnical(text: string): boolean {
  const value = text.trim();
  if (!value) {
    return true;
  }
  const lower = value.toLowerCase();
  return (
    /unexpected token/i.test(value) ||
    /internal server error/i.test(value) ||
    /traceback|syntaxerror|typeerror|referenceerror|json\.parse/i.test(value) ||
    /^error[:\s]/i.test(value) ||
    /^error$/i.test(value) ||
    /^<!doctype/i.test(value) ||
    value.startsWith("{") ||
    value.startsWith("[") ||
    /\b(500|502|503|504)\b/.test(value) ||
    /\/Users\/|\/home\/|\\\\/.test(value) ||
    lower.includes("status code") ||
    lower.includes("failed to fetch")
  );
}

export function messageForHttpStatus(status: number | null): string {
  if (status === null) {
    return "We could not reach Brasaland Digital. Confirm the staff API is running, then try again.";
  }
  if (status === 400) {
    return "That request could not be processed. Check what you entered and try again.";
  }
  if (status === 401) {
    return "Email or password did not match, or your session expired. Sign in and try again.";
  }
  if (status === 403) {
    return "You do not have access to this action.";
  }
  if (status === 404) {
    return "We could not find that record.";
  }
  if (status === 409) {
    return "An account with that email already exists. Sign in instead.";
  }
  if (status === 422) {
    return "Please correct the highlighted fields and try again.";
  }
  if (status === 429) {
    return "Too many attempts. Wait a moment and try again.";
  }
  if (status >= 500) {
    return "Brasaland Digital is having trouble right now. Try again in a moment.";
  }
  return "Something went wrong. Try again, or contact Brasaland Digital if it continues.";
}

function friendlyFromDetails(details: unknown): string | null {
  if (typeof details !== "string") {
    return null;
  }
  if (looksTechnical(details) || details.length > 180) {
    return null;
  }
  return details;
}

export function toUserFacingMessage(error: unknown, fallback?: string): string {
  if (error instanceof ApiError) {
    return friendlyFromDetails(error.details) ?? messageForHttpStatus(error.status);
  }
  if (error instanceof Error && !looksTechnical(error.message)) {
    return error.message;
  }
  return fallback ?? messageForHttpStatus(null);
}

export function sanitizeFieldMessage(message: unknown): string {
  if (typeof message === "string" && !looksTechnical(message)) {
    return message;
  }
  return "Check this field and try again.";
}

function explainHttpFailure(status: number, details: unknown): string {
  if (Array.isArray(details)) {
    return messageForHttpStatus(422);
  }
  return friendlyFromDetails(details) ?? messageForHttpStatus(status);
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

  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers,
    });
  } catch {
    throw new ApiError(messageForHttpStatus(null), null, null);
  }

  if (response.status === 401 && token && !isPublicAuthCall) {
    clearSessionAndRedirectToLogin();
  }

  if (!response.ok) {
    let details: unknown = null;
    let message = explainHttpFailure(response.status, null);
    try {
      const body = (await response.json()) as { detail?: unknown; message?: string };
      details = body.detail ?? null;
      const announced = typeof body.message === "string" ? body.message : null;
      message =
        announced && announced.trim() && !looksTechnical(announced)
          ? announced
          : explainHttpFailure(response.status, details);
    } catch {
      try {
        await response.text();
      } catch {
        /* body is unreadable; ignore raw text */
      }
    }
    throw new ApiError(message, details, response.status);
  }

  if (response.status === 204) {
    return null as T;
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(messageForHttpStatus(response.status), null, response.status);
  }
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

/** CONTEXT-company.md KPI row from reporting.weekly_location_performance. */
export type WeeklyLocationPerformanceRow = {
  location_id: string;
  country: string;
  currency: "COP" | "USD" | string;
  total_purchase_cost: number;
  total_waste_cost: number;
  waste_ratio: number;
  stockout_events_count: number;
  price_alert_events_count: number;
};

export type WeeklyLocationPerformanceResponse = {
  week_start: string | null;
  locations: WeeklyLocationPerformanceRow[];
};

export type PipelineRunLatest = {
  run_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  records_processed?: number | null;
  status?: string | null;
  error_message?: string | null;
  message?: string | null;
};

/** Phase four dashboard — Mariana / Felipe / Lucía weekly location KPIs. */
export async function fetchWeeklyLocationPerformance(
  weekStart?: string,
): Promise<WeeklyLocationPerformanceResponse> {
  const query = weekStart
    ? `?week_start=${encodeURIComponent(weekStart)}`
    : "";
  return apiRequest<WeeklyLocationPerformanceResponse>(
    `/reporting/weekly-location-performance${query}`,
  );
}

export async function fetchLatestPipelineRun(): Promise<PipelineRunLatest> {
  return apiRequest<PipelineRunLatest>("/reporting/pipeline-runs/latest");
}
