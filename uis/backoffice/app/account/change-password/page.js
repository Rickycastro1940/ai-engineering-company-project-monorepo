"use client";

import { useState } from "react";
import ProtectedRoute from "../../../components/ProtectedRoute";
import { apiRequest } from "../../../lib/api";

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const changePassword = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation must match.");
      return;
    }

    try {
      await apiRequest("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password changed.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  return (
    <ProtectedRoute>
      <main className="page-shell">
        <section className="hero">
          <p className="eyebrow">Account management</p>
          <h1>Change password</h1>
          <p>Confirm your new password before updating your account credentials.</p>
        </section>

        <section className="card narrow">
          <form className="form-stack" onSubmit={changePassword}>
            <label>
              Current password
              <input
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </label>
            <label>
              New password
              <input
                type="password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                type="password"
                minLength={8}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />
            </label>
            {error ? <p className="error">{error}</p> : null}
            {message ? <p className="success">{message}</p> : null}
            <button type="submit">Change password</button>
          </form>
        </section>
      </main>
    </ProtectedRoute>
  );
}
