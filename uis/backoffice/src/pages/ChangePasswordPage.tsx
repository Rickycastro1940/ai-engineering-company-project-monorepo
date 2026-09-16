import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthProvider";
import { updateUser } from "../lib/api";
import "./AuthPages.css";

export function ChangePasswordPage() {
  const { user } = useAuth();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation must match.");
      return;
    }
    if (!user) {
      setError("Not authenticated.");
      return;
    }

    try {
      await updateUser(user.id, { password: newPassword });
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password changed. Use the new password on the next login.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to change password.");
    }
  }

  return (
    <section className="auth-card auth-card--embedded">
      <p className="auth-card__eyebrow">Account</p>
      <h2>Change password</h2>
      <p className="auth-card__lead">
        Confirmation is checked in the browser, then the password is updated with{" "}
        <code>PUT /users/{"{id}"}</code>.
      </p>
      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          New password
          <input
            type="password"
            autoComplete="new-password"
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
            autoComplete="new-password"
            minLength={8}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
          />
        </label>
        {error ? (
          <p className="auth-form__error" role="alert">
            {error}
          </p>
        ) : null}
        {message ? <p className="auth-form__success">{message}</p> : null}
        <button type="submit">Change password</button>
      </form>
    </section>
  );
}
