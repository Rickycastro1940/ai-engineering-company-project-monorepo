/**
 * Kitchen inventory API client for Brasaland Restaurant Operations.
 * Components must import these helpers — never call fetch() for /inventory.
 */
import { clearSessionAndRedirectToLogin, getStoredToken } from "./api";

export type InventoryProduct = {
  product_id: number;
  name: string;
  quantity: number;
  unit: string;
};

export type InventoryProductCreate = {
  name: string;
  quantity: number;
  unit: string;
};

export class InventoryApiError extends Error {
  status: number | null;
  body: unknown;

  constructor(message: string, status: number | null = null, body: unknown = null) {
    super(message);
    this.name = "InventoryApiError";
    this.status = status;
    this.body = body;
  }
}

export function inventoryApiBaseUrl(): string {
  const configured =
    import.meta.env.NEXT_PUBLIC_INVENTORY_API_URL ??
    import.meta.env.VITE_INVENTORY_API_URL ??
    "";
  return String(configured).trim().replace(/\/$/, "");
}

export function inventoryApiUrl(path: string): string {
  const base = inventoryApiBaseUrl();
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${suffix}` : suffix;
}

function textFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return null;
}

/** Pull a human-readable message from FastAPI / Brasaland error JSON. */
export function extractInventoryErrorMessage(body: unknown, rawText: string, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const fromMessage = textFromUnknown(record.message);
    if (fromMessage) {
      return fromMessage;
    }
    const detail = record.detail;
    const fromDetail = textFromUnknown(detail);
    if (fromDetail) {
      return fromDetail;
    }
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return textFromUnknown((item as { msg?: unknown }).msg);
          }
          return textFromUnknown(item);
        })
        .filter((part): part is string => Boolean(part));
      if (parts.length > 0) {
        return parts.join(" ");
      }
    }
  }
  if (rawText.trim()) {
    return rawText.trim();
  }
  return `Kitchen inventory request failed (HTTP ${status}).`;
}

export function inventoryErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof InventoryApiError && error.message.trim()) {
    return error.message;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

async function inventoryRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  if (!token) {
    throw new InventoryApiError(
      "Sign in to manage kitchen inventory. Your session token was not found.",
      401,
    );
  }

  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(inventoryApiUrl(path), {
      ...options,
      headers,
    });
  } catch {
    throw new InventoryApiError(
      "We could not reach the kitchen inventory API. Confirm the Brasaland API is running, then try again.",
      null,
    );
  }

  if (response.status === 401) {
    clearSessionAndRedirectToLogin();
  }

  if (response.status >= 400) {
    const rawText = await response.text();
    let parsed: unknown = null;
    if (rawText) {
      try {
        parsed = JSON.parse(rawText) as unknown;
      } catch {
        parsed = null;
      }
    }
    throw new InventoryApiError(
      extractInventoryErrorMessage(parsed, rawText, response.status),
      response.status,
      parsed ?? rawText,
    );
  }

  if (response.status === 204) {
    return null as T;
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new InventoryApiError(
      `Kitchen inventory returned an unreadable response (HTTP ${response.status}).`,
      response.status,
    );
  }
}

export async function listInventory(): Promise<InventoryProduct[]> {
  return inventoryRequest<InventoryProduct[]>("/inventory");
}

export async function createInventoryProduct(
  payload: InventoryProductCreate,
): Promise<InventoryProduct> {
  return inventoryRequest<InventoryProduct>("/inventory", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateInventoryStock(
  productId: number,
  delta: number,
): Promise<InventoryProduct> {
  return inventoryRequest<InventoryProduct>(
    `/inventory/${encodeURIComponent(String(productId))}`,
    {
      method: "PATCH",
      body: JSON.stringify({ delta }),
    },
  );
}

export async function listInventoryAlerts(threshold = 10): Promise<InventoryProduct[]> {
  const query = new URLSearchParams({ threshold: String(threshold) });
  return inventoryRequest<InventoryProduct[]>(`/inventory/alerts?${query}`);
}

/** @deprecated Prefer listInventory — kept for existing page imports. */
export const fetchInventory = listInventory;
/** @deprecated Prefer listInventoryAlerts. */
export const fetchInventoryAlerts = listInventoryAlerts;
