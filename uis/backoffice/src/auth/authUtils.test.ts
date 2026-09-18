import {
  AUTH_TOKEN_KEY,
  clearAuthToken,
  extractAccessToken,
  getAuthToken,
  isJwtFormat,
  isValidEmail,
  isValidPassword,
  passwordsMatch,
  storeAuthToken,
} from "./authUtils";

function makeJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.signature`;
}

describe("extractAccessToken", () => {
  test("happy path: keeps a non-empty access token", () => {
    expect(extractAccessToken({ access_token: "  aaa.bbb.ccc  " })).toBe("aaa.bbb.ccc");
  });

  test("failure: login payload without a token is not a session", () => {
    expect(() => extractAccessToken({})).toThrow("Login did not return an access token.");
  });
});

describe("isJwtFormat", () => {
  test("happy path: three non-empty segments", () => {
    expect(isJwtFormat("aaa.bbb.ccc")).toBe(true);
  });

  test("failure: missing segments is not a staff JWT", () => {
    expect(isJwtFormat("")).toBe(false);
    expect(isJwtFormat("only-one-part")).toBe(false);
  });
});

describe("storeAuthToken / getAuthToken / clearAuthToken", () => {
  test("happy path: persists a JWT for the staff console", () => {
    const token = makeJwt({ sub: "1", exp: 2_000_000_000 });
    storeAuthToken(token);
    expect(getAuthToken()).toBe(token);
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBe(token);
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
  });

  test("failure: will not persist a malformed token", () => {
    expect(() => storeAuthToken("not-a-jwt")).toThrow("Refusing to store a malformed JWT.");
    // Rejecting the write must leave the console unauthenticated.
    expect(getAuthToken()).toBeNull();
  });
});

describe("isValidEmail", () => {
  test("happy path: accepts a staff mailbox", () => {
    expect(isValidEmail("felipe.guerrero@brasaland.test")).toBe(true);
  });

  test("failure: rejects a value that is not a mailbox", () => {
    expect(isValidEmail("not-an-email")).toBe(false);
  });
});

describe("isValidPassword", () => {
  test("happy path: eight or more characters meet the policy", () => {
    expect(isValidPassword("secret-password")).toBe(true);
  });

  test("failure: shorter than eight is not accepted", () => {
    expect(isValidPassword("short")).toBe(false);
  });
});

describe("passwordsMatch", () => {
  test("happy path: matching non-empty passwords", () => {
    expect(passwordsMatch("secret-password", "secret-password")).toBe(true);
  });

  test("failure: mismatch or empty confirmation is not a change", () => {
    expect(passwordsMatch("secret-password", "other")).toBe(false);
    // Two empty strings are equal, but that is not a password the kitchen can use.
    expect(passwordsMatch("", "")).toBe(false);
  });
});
