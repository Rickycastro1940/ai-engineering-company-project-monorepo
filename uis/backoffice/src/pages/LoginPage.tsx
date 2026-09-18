import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { FetchError, Spinner } from "../components/AsyncState";
import { ApiError, SUPPORT_PROMPT, loginUser, sanitizeFieldMessage, storeToken, toUserFacingMessage } from "../lib/api";
import "./AuthPages.css";

type FieldErrors = {
  email?: string;
  password?: string;
};

function mapApiValidationErrors(details: unknown): FieldErrors {
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
  }
  return errors;
}

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { signIn, isAuthenticated, isLoading, sessionError, retrySession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const nextPath = searchParams.get("next") || "/accessible";

  if (isLoading) {
    return (
      <main className="auth-shell">
        <section className="auth-card" aria-busy="true">
          <Spinner label="Checking your session…" />
        </section>
      </main>
    );
  }

  if (sessionError) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <p className="auth-card__eyebrow">Brasaland Digital</p>
          <h1>Could not verify session</h1>
          <FetchError
            message={sessionError}
            onRetry={retrySession}
            retryLabel="Retry session check"
            homeTo="/register"
            homeLabel="Create an account"
          />
        </section>
      </main>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={nextPath} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    setIsSubmitting(true);
    try {
      let authResponse;
      try {
        authResponse = await loginUser(email, password);
      } catch (requestError) {
        setError(toUserFacingMessage(requestError, "We could not sign you in. Check your email and password."));
        if (requestError instanceof ApiError) {
          setFieldErrors(mapApiValidationErrors(requestError.details));
        }
        return;
      }
      if (!authResponse?.access_token) {
        setError("Sign-in did not return a session. Try again.");
        return;
      }
      storeToken(authResponse.access_token);
      try {
        await signIn(authResponse);
      } catch (requestError) {
        setError(
          toUserFacingMessage(
            requestError,
            "Signed in, but the session could not be loaded. Try again.",
          ),
        );
        return;
      }
      navigate(nextPath, { replace: true });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="auth-card__eyebrow">Brasaland Digital</p>
        <h1>Staff login</h1>
        <p className="auth-card__lead">
          Email and password. On success the JWT is stored in localStorage and you
          enter the operations console.
        </p>
        <form onSubmit={handleSubmit} className="auth-form" noValidate>
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
              autoComplete="current-password"
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
              <p className="auth-form__support">{SUPPORT_PROMPT}</p>
            </div>
          ) : null}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? (
              <span className="async-state">
                <span className="async-state__spinner" aria-hidden="true" />
                Signing in…
              </span>
            ) : error ? (
              "Try again"
            ) : (
              "Sign in"
            )}
          </button>
        </form>
        <p className="auth-card__muted">
          Need an account? <Link to="/register">Create one</Link>
        </p>
      </section>
    </main>
  );
}
