/**
 * Client-side staff-session helpers for the Brasaland backoffice.
 * JWTs are issued by FastAPI; this module only stores and validates shape.
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
  if (!token) {
    return false;
  }
  const parts = token.split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
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

export function isValidEmail(email: string): boolean {
  return EMAIL_PATTERN.test(email.trim());
}

export function isValidPassword(password: string): boolean {
  return password.length >= 8;
}

export function passwordsMatch(password: string, confirmation: string): boolean {
  return password.length > 0 && password === confirmation;
}
