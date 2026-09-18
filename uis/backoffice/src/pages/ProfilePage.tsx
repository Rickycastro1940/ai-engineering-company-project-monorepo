import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { FetchError, Spinner } from "../components/AsyncState";
import { useAuth } from "../auth/AuthProvider";
import {
  SUPPORT_PROMPT,
  fetchCurrentUser,
  toUserFacingMessage,
  updateMyProfile,
} from "../lib/api";
import "./AuthPages.css";

export function ProfilePage() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadStatus, setLoadStatus] = useState<"loading" | "success" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [loadNonce, setLoadNonce] = useState(0);
  const [isSaving, setIsSaving] = useState(false);

  const retryLoad = useCallback(() => {
    setLoadNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";

    async function load() {
      setLoadStatus("loading");
      setLoadError("");
      setError("");
      try {
        const profile = await fetchCurrentUser();
        if (cancelled) {
          return;
        }
        setUser(profile);
        setName(profile?.name ?? "");
        setPhone(profile?.phone ?? "");
        setAddress(profile?.address ?? "");
        outcome = "success";
      } catch (requestError) {
        if (!cancelled) {
          setLoadError(
            toUserFacingMessage(requestError, "Your profile could not be loaded right now."),
          );
        }
      } finally {
        if (!cancelled) {
          setLoadStatus(outcome);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [setUser, loadNonce]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setIsSaving(true);
    try {
      const updatedUser = await updateMyProfile({
        name: name.trim(),
        phone: phone.trim(),
        address: address.trim(),
      });
      setUser(updatedUser);
      setName(updatedUser?.name ?? "");
      setPhone(updatedUser?.phone ?? "");
      setAddress(updatedUser?.address ?? "");
      setMessage("Profile updated.");
    } catch (requestError) {
      setError(toUserFacingMessage(requestError, "Your profile could not be saved."));
    } finally {
      setIsSaving(false);
    }
  }

  if (loadStatus === "loading") {
    return (
      <section className="auth-card auth-card--embedded" aria-busy="true">
        <Spinner label="Loading profile…" />
      </section>
    );
  }

  if (loadStatus === "error") {
    return (
      <section className="auth-card auth-card--embedded">
        <p className="auth-card__eyebrow">Account</p>
        <h2>Profile</h2>
        <FetchError message={loadError} onRetry={retryLoad} />
      </section>
    );
  }

  return (
    <section className="auth-card auth-card--embedded">
      <p className="auth-card__eyebrow">Account</p>
      <h2>Profile</h2>
      <p className="auth-card__lead">
        Email and contact details from <code>GET /auth/me</code>. Name, phone, and
        address are saved with <code>PUT /profiles/me</code>.
      </p>
      <dl className="auth-meta">
        <div>
          <dt>Email</dt>
          <dd>{user?.email ?? "—"}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{user?.is_admin ? "admin" : "staff"}</dd>
        </div>
      </dl>
      <form className="auth-form" onSubmit={handleSubmit} aria-busy={isSaving}>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" />
        </label>
        <label>
          Phone
          <input
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            autoComplete="tel"
            inputMode="tel"
          />
        </label>
        <label>
          Address
          <textarea
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            autoComplete="street-address"
            rows={3}
          />
        </label>
        {error ? (
          <div className="auth-form__error" role="alert">
            <p>{error}</p>
            <p>
              Use Save profile to try again, or go to{" "}
              <Link to="/accessible">operations home</Link>.
            </p>
            <p className="auth-form__support">{SUPPORT_PROMPT}</p>
          </div>
        ) : null}
        {message ? <p className="auth-form__success">{message}</p> : null}
        <button type="submit" disabled={isSaving}>
          {isSaving ? (
            <span className="async-state">
              <span className="async-state__spinner" aria-hidden="true" />
              Saving…
            </span>
          ) : error ? (
            "Try again"
          ) : (
            "Save profile"
          )}
        </button>
      </form>
    </section>
  );
}
