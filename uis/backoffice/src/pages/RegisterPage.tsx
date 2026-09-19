import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { isValidEmail, isValidPassword } from "../auth/authUtils";
import { ApiError, SUPPORT_PROMPT, createUserAccount, loginUser, sanitizeFieldMessage, storeToken, toUserFacingMessage } from "../lib/api";
import "./AuthPages.css";

type FieldErrors = {
  name?: string;
  email?: string;
  password?: string;
};

function buildValidationErrors(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!isValidEmail(email)) {
    errors.email = "A valid email is required.";
  }
  if (!isValidPassword(password)) {
    errors.password = "Password must be at least 8 characters.";
  }
  return errors;
}

function mapApiValidationErrors(details: unknown): FieldErrors {
  if (typeof details === "string") {
    if (details.toLowerCase().includes("email")) {
      return { email: sanitizeFieldMessage(details) };
    }
    return {};
  }
  if (!Array.isArray(details)) {
    return {};
  }
  const errors: FieldErrors = {};
  for (const item of details) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const loc = "loc" in item ? item.loc : undefined;
    const msg = "msg" in item ? item.msg : undefined;
    const field = Array.isArray(loc) ? loc?.[loc.length - 1] : undefined;
    if (field === "email" && typeof msg === "string") {
      errors.email = sanitizeFieldMessage(msg);
    }
    if (field === "password" && typeof msg === "string") {
      errors.password = sanitizeFieldMessage(msg);
    }
    if (field === "name" && typeof msg === "string") {
      errors.name = sanitizeFieldMessage(msg);
    }
  }
  return errors;
}

export function RegisterPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const validationErrors = buildValidationErrors(email, password);
    setFieldErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      return;
    }
    setIsSubmitting(true);
    try {
      try {
        await createUserAccount({
          email,
          password,
          name: name.trim() || undefined,
        });
      } catch (requestError) {
        setError(toUserFacingMessage(requestError, "We could not create your account. Try again."));
        if (requestError instanceof ApiError) {
          setFieldErrors(mapApiValidationErrors(requestError.details));
        }
        return;
      }
      let authResponse;
      try {
        authResponse = await loginUser(email, password);
      } catch (requestError) {
        setError(
          toUserFacingMessage(
            requestError,
            "Your account was created, but sign-in did not finish. Try signing in.",
          ),
        );
        return;
      }
      if (!authResponse?.access_token) {
        setError("Your account was created, but sign-in did not finish. Try signing in.");
        return;
      }
      storeToken(authResponse.access_token);
      try {
        await signIn(authResponse);
      } catch (requestError) {
        setError(
          toUserFacingMessage(
            requestError,
            "Your account was created, but the session could not be loaded. Try signing in.",
          ),
        );
        return;
      }
      navigate("/accessible", { replace: true });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="auth-card__eyebrow">New operator</p>
        <h1>Create an account</h1>
        <p className="auth-card__lead">
          Registers with <code>POST /users</code> (name is optional), then signs in
          with <code>POST /auth/login</code> using the same credentials.
        </p>
        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          <label>
            Name <span className="auth-card__optional">(optional)</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="name"
              aria-invalid={Boolean(fieldErrors.name)}
            />
            {fieldErrors.name ? <span className="auth-form__field-error">{fieldErrors.name}</span> : null}
          </label>
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(fieldErrors.email)}
              required
            />
            {fieldErrors.email ? <span className="auth-form__field-error">{fieldErrors.email}</span> : null}
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(fieldErrors.password)}
              required
            />
            {fieldErrors.password ? (
              <span className="auth-form__field-error">{fieldErrors.password}</span>
            ) : null}
          </label>
          {error ? (
            <div className="auth-form__error" role="alert">
              <p>{error}</p>
              <p>
                You can also <Link to="/login">return to login</Link>.
              </p>
              <p className="auth-form__support">{SUPPORT_PROMPT}</p>
            </div>
          ) : null}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? (
              <span className="async-state">
                <span className="async-state__spinner" aria-hidden="true" />
                Creating account…
              </span>
            ) : error ? (
              "Try again"
            ) : (
              "Create account"
            )}
          </button>
        </form>
        <p className="auth-card__muted">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
