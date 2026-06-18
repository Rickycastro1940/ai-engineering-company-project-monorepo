"use client";

import { useEffect, useState } from "react";
import ProtectedRoute from "../../../components/ProtectedRoute";
import { useAuth } from "../../../components/AuthProvider";
import { apiRequest } from "../../../lib/api";

export default function AccountProfilePage() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (user?.name) {
      setName(user.name);
    }
  }, [user]);

  const updateProfile = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const updatedUser = await apiRequest(`/users/${encodeURIComponent(user.id)}`, {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
      setUser(updatedUser);
      setMessage("Profile updated.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  return (
    <ProtectedRoute>
      <main className="page-shell">
        <section className="hero">
          <p className="eyebrow">Account management</p>
          <h1>Profile</h1>
          <p>View your account details and update your display name.</p>
        </section>

        <section className="card narrow">
          <h2>Profile details</h2>
          <p className="muted">Email: {user?.email}</p>
          <form className="form-stack" onSubmit={updateProfile}>
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            {error ? <p className="error">{error}</p> : null}
            {message ? <p className="success">{message}</p> : null}
            <button type="submit">Save profile</button>
          </form>
        </section>
      </main>
    </ProtectedRoute>
  );
}
