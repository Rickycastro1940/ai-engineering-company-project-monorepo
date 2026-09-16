import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthProvider";
import { fetchCurrentUser, updateMyProfile } from "../lib/api";
import "./AuthPages.css";

export function ProfilePage() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError("");
      try {
        const profile = await fetchCurrentUser();
        if (cancelled) {
          return;
        }
        setUser(profile);
        setName(profile.name ?? "");
        setPhone(profile.phone ?? "");
        setAddress(profile.address ?? "");
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Unable to load profile.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [setUser]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const updatedUser = await updateMyProfile({
        name: name.trim(),
        phone: phone.trim(),
        address: address.trim(),
      });
      setUser(updatedUser);
      setName(updatedUser.name ?? "");
      setPhone(updatedUser.phone ?? "");
      setAddress(updatedUser.address ?? "");
      setMessage("Profile updated.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to update profile.");
    }
  }

  if (isLoading && !user) {
    return (
      <section className="auth-card auth-card--embedded" aria-busy="true">
        <p>Loading profile…</p>
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
          <dd>{user?.email}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{user?.is_admin ? "admin" : "staff"}</dd>
        </div>
      </dl>
      <form className="auth-form" onSubmit={handleSubmit}>
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
          <p className="auth-form__error" role="alert">
            {error}
          </p>
        ) : null}
        {message ? <p className="auth-form__success">{message}</p> : null}
        <button type="submit">Save profile</button>
      </form>
    </section>
  );
}
