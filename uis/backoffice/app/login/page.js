"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "../../components/AuthProvider";
import { loginUser } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const authResponse = await loginUser(email, password);
      signIn(authResponse);
      const next = new URLSearchParams(window.location.search).get("next") || "/";
      router.replace(next);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="page-shell auth-page">
      <section className="card narrow">
        <p className="eyebrow">Welcome back</p>
        <h1>Login</h1>
        <form onSubmit={handleSubmit} className="form-stack">
          <label>
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          {error ? <p className="error">{error}</p> : null}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="muted">
          Need an account? <Link href="/register">Create one</Link>
        </p>
      </section>
    </main>
  );
}
