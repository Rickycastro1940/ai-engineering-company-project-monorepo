/**
 * Client-side auth helpers for the Brasaland staff console.
 * JWTs are issued by FastAPI; this module only stores, decodes, and validates shape.
 */

export const AUTH_TOKEN_KEY = "auth_token";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function extractAccessToken(payload: { access_token?: unknown }): string {
  if (typeof payload.access_token !== "string" || !payload.access_token.trim()) {
    throw new Error("Login did not return an access token.");
  }
  return payload.access_token.trim();
}

export function isJwtFormat(token: string): boolean {
  if (!token || typeof token !== "string") {
    return false;
  }
  const parts = token.split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

export type JwtPayload = {
  sub?: string;
  exp?: number;
};

function base64UrlToJson(segment: string): unknown {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padLength = (4 - (padded.length % 4)) % 4;
  const json = atob(`${padded}${"=".repeat(padLength)}`);
  return JSON.parse(json) as unknown;
}

export function decodeJwtPayload(token: string): JwtPayload {
  if (!isJwtFormat(token)) {
    throw new Error("Malformed JWT.");
  }
  try {
    const payload = base64UrlToJson(token.split(".")[1]);
    if (!payload || typeof payload !== "object") {
      throw new Error("JWT payload is not valid JSON.");
    }
    return payload as JwtPayload;
  } catch (error) {
    if (error instanceof Error && error.message === "Malformed JWT.") {
      throw error;
    }
    throw new Error("JWT payload is not valid JSON.");
  }
}

export function isJwtExpired(token: string, nowMs: number = Date.now()): boolean {
  const payload = decodeJwtPayload(token);
  if (typeof payload.exp !== "number") {
    throw new Error("JWT is missing an expiry.");
  }
  return payload.exp * 1000 <= nowMs;
}

export function storeAuthToken(token: string, storage: Storage = localStorage): void {
  const normalized = extractAccessToken({ access_token: token });
  if (!isJwtFormat(normalized)) {
    throw new Error("Refusing to store a malformed JWT.");
  }
  storage.setItem(AUTH_TOKEN_KEY, normalized);
}

export function getAuthToken(storage: Storage = localStorage): string | null {
  return storage.getItem(AUTH_TOKEN_KEY);
}

export function clearAuthToken(storage: Storage = localStorage): void {
  storage.removeItem(AUTH_TOKEN_KEY);
}

export function authorizationHeader(token: string | null): { Authorization: string } {
  if (!token) {
    throw new Error("No session token.");
  }
  return { Authorization: `Bearer ${token}` };
}

export function isValidEmail(email: string): boolean {
  return EMAIL_PATTERN.test(email.trim());
}

export function isValidPassword(password: string): boolean {
  return password.length >= 8;
}

export function passwordsMatch(password: string, confirmation: string): boolean {
  return password.length > 0 && password === confirmation;
}

export async function sha256Hex(value: string): Promise<string> {
  if (!value) {
    throw new Error("Cannot hash an empty value.");
  }
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new Error("Web Crypto is unavailable.");
  }
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
