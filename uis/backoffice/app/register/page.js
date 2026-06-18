"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "../../components/AuthProvider";
import { registerUser } from "../../lib/api";

function buildValidationErrors(name, email, password) {
  const errors = {};
  if (!name.trim()) {
    errors.name = "Name is required.";
  }
  if (!email.trim() || !email.includes("@")) {
    errors.email = "A valid email is required.";
  }
  if (password.length < 8) {
    errors.password = "Password must be at least 8 characters.";
  }
  return errors;
}

function mapApiValidationErrors(details) {
  if (!Array.isArray(details)) {
    return {};
  }
  return details.reduce((errors, item) => {
    const field = item.loc?.[item.loc.length - 1];
    if (field) {
      errors[field] = item.msg;
    }
    return errors;
  }, {});
}

export default function RegisterPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    const validationErrors = buildValidationErrors(name, email, password);
    setFieldErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      return;
    }
    setIsSubmitting(true);
    try {
      const authResponse = await registerUser(name, email, password);
      signIn(authResponse);
      router.replace("/");
    } catch (requestError) {
      setError(requestError.message);
      setFieldErrors(mapApiValidationErrors(requestError.details));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="page-shell auth-page">
      <section className="card narrow">
        <p className="eyebrow">New user</p>
        <h1>Create an account</h1>
        <form onSubmit={handleSubmit} className="form-stack" noValidate>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} aria-invalid={Boolean(fieldErrors.name)} required />
            {fieldErrors.name ? <span className="field-error">{fieldErrors.name}</span> : null}
          </label>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(fieldErrors.email)}
              required
            />
            {fieldErrors.email ? <span className="field-error">{fieldErrors.email}</span> : null}
          </label>
          <label>
            Password
            <input
              type="password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(fieldErrors.password)}
              required
            />
            {fieldErrors.password ? <span className="field-error">{fieldErrors.password}</span> : null}
          </label>
          {error ? <p className="error">{error}</p> : null}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>
        <p className="muted">
          Already registered? <Link href="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
