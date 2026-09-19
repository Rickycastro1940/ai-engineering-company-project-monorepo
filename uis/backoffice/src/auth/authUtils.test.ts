import {
  AUTH_TOKEN_KEY,
  authorizationHeader,
  clearAuthToken,
  decodeJwtPayload,
  extractAccessToken,
  getAuthToken,
  isJwtExpired,
  isJwtFormat,
  isValidEmail,
  isValidPassword,
  passwordsMatch,
  sha256Hex,
  storeAuthToken,
} from "./authUtils";

function encodeSegment(value: string): string {
  return Buffer.from(value, "utf8").toString("base64url");
}

function makeJwt(payload: Record<string, unknown>): string {
  return `${encodeSegment(JSON.stringify({ alg: "HS256", typ: "JWT" }))}.${encodeSegment(
    JSON.stringify(payload),
  )}.signature`;
}

describe("extractAccessToken", () => {
  test("happy path returns a trimmed access token", () => {
    expect(extractAccessToken({ access_token: "  abc.def.ghi  " })).toBe("abc.def.ghi");
  });

  test("failure mode rejects a missing token", () => {
    expect(() => extractAccessToken({})).toThrow("Login did not return an access token.");
    expect(() => extractAccessToken({ access_token: "   " })).toThrow(
      "Login did not return an access token.",
    );
  });
});

describe("isJwtFormat", () => {
  test("happy path accepts a three-part token", () => {
    expect(isJwtFormat("aaa.bbb.ccc")).toBe(true);
  });

  test("failure mode rejects malformed tokens", () => {
    expect(isJwtFormat("")).toBe(false);
    expect(isJwtFormat("only-one-part")).toBe(false);
    expect(isJwtFormat("missing.signature.")).toBe(false);
  });
});

describe("decodeJwtPayload", () => {
  test("happy path reads sub and exp", () => {
    const token = makeJwt({ sub: "8", exp: 1_800_000_000 });
    expect(decodeJwtPayload(token)).toEqual({ sub: "8", exp: 1_800_000_000 });
  });

  test("failure mode rejects a malformed JWT", () => {
    expect(() => decodeJwtPayload("not-a-jwt")).toThrow("Malformed JWT.");
    expect(() => decodeJwtPayload("aaa.%%%-not-json.ccc")).toThrow("JWT payload is not valid JSON.");
  });
});

describe("isJwtExpired", () => {
  test("happy path returns false before exp", () => {
    const token = makeJwt({ sub: "1", exp: 2_000_000_000 });
    expect(isJwtExpired(token, 1_000_000_000_000)).toBe(false);
  });

  test("failure mode returns true after exp and errors without exp", () => {
    const expired = makeJwt({ sub: "1", exp: 1_000 });
    expect(isJwtExpired(expired, 1_000_000_000_000)).toBe(true);
    expect(() => isJwtExpired(makeJwt({ sub: "1" }))).toThrow("JWT is missing an expiry.");
  });
});

describe("storeAuthToken / getAuthToken / clearAuthToken", () => {
  test("happy path stores and clears the staff JWT", () => {
    const token = makeJwt({ sub: "1", exp: 2_000_000_000 });
    storeAuthToken(token);
    expect(getAuthToken()).toBe(token);
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBe(token);
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
  });

  test("failure mode refuses to persist a malformed token", () => {
    expect(() => storeAuthToken("not-a-jwt")).toThrow("Refusing to store a malformed JWT.");
    expect(getAuthToken()).toBeNull();
  });
});

describe("authorizationHeader", () => {
  test("happy path builds a Bearer header", () => {
    expect(authorizationHeader("abc.def.ghi")).toEqual({ Authorization: "Bearer abc.def.ghi" });
  });

  test("failure mode rejects a missing session token", () => {
    expect(() => authorizationHeader(null)).toThrow("No session token.");
    expect(() => authorizationHeader("")).toThrow("No session token.");
  });
});

describe("isValidEmail", () => {
  test("happy path accepts a staff mailbox", () => {
    expect(isValidEmail("felipe.guerrero@brasaland.test")).toBe(true);
  });

  test("failure mode rejects blank or invalid email", () => {
    expect(isValidEmail("")).toBe(false);
    expect(isValidEmail("not-an-email")).toBe(false);
  });
});

describe("isValidPassword", () => {
  test("happy path accepts eight or more characters", () => {
    expect(isValidPassword("secret-password")).toBe(true);
  });

  test("failure mode rejects a short password", () => {
    expect(isValidPassword("short")).toBe(false);
  });
});

describe("passwordsMatch", () => {
  test("happy path accepts matching non-empty passwords", () => {
    expect(passwordsMatch("secret-password", "secret-password")).toBe(true);
  });

  test("failure mode rejects mismatch or empty values", () => {
    expect(passwordsMatch("secret-password", "other-password")).toBe(false);
    expect(passwordsMatch("", "")).toBe(false);
  });
});

describe("sha256Hex", () => {
  test("happy path hashes UTF-8 text", async () => {
    const digest = await sha256Hex("brasaland");
    expect(digest).toHaveLength(64);
    expect(digest).toBe(await sha256Hex("brasaland"));
    expect(digest).not.toBe(await sha256Hex("other"));
  });

  test("failure mode rejects an empty value", async () => {
    await expect(sha256Hex("")).rejects.toThrow("Cannot hash an empty value.");
  });
});
