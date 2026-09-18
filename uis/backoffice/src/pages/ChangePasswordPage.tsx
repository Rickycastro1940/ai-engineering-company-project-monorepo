import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { SUPPORT_PROMPT, toUserFacingMessage, updateUser } from "../lib/api";
import "./AuthPages.css";

export function ChangePasswordPage() {
  const { user } = useAuth();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation must match.");
      return;
    }
    if (user?.id == null) {
      setError("You are not signed in. Return to login and try again.");
      return;
    }

    setIsSaving(true);
    try {
      await updateUser(user.id, { password: newPassword });
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password changed. Use the new password on the next login.");
    } catch (requestError) {
      setError(toUserFacingMessage(requestError, "Your password could not be changed."));
    } finally {
      setIsSaving(false);
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
          <div className="auth-form__error" role="alert">
            <p>{error}</p>
            <p>
              {user?.id == null ? (
                <Link to="/login">Return to login</Link>
              ) : (
                <>
                  Use the button below to try again, or go to{" "}
                  <Link to="/accessible">operations home</Link>.
                </>
              )}
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
            "Change password"
          )}
        </button>
      </form>
    </section>
  );
}
