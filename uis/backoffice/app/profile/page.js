"use client";

import { useEffect, useState } from "react";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../components/AuthProvider";
import { apiRequest } from "../../lib/api";

export default function ProfilePage() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");

  useEffect(() => {
    if (user?.name) {
      setName(user.name);
    }
  }, [user]);

  const updateProfile = async (event) => {
    event.preventDefault();
    setProfileError("");
    setProfileMessage("");
    try {
      const updatedUser = await apiRequest("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      setUser(updatedUser);
      setProfileMessage("Profile updated.");
    } catch (requestError) {
      setProfileError(requestError.message);
    }
  };

  const changePassword = async (event) => {
    event.preventDefault();
    setPasswordError("");
    setPasswordMessage("");
    try {
      await apiRequest("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setPasswordMessage("Password changed.");
    } catch (requestError) {
      setPasswordError(requestError.message);
    }
  };

  return (
    <ProtectedRoute>
      <main className="page-shell">
        <section className="hero">
          <p className="eyebrow">Account management</p>
          <h1>Profile</h1>
          <p>Manage your identity and password for protected backoffice access.</p>
        </section>

        <div className="grid-two">
          <section className="card">
            <h2>Profile details</h2>
            <p className="muted">{user?.email}</p>
            <form className="form-stack" onSubmit={updateProfile}>
              <label>
                Name
                <input value={name} onChange={(event) => setName(event.target.value)} required />
              </label>
              {profileError ? <p className="error">{profileError}</p> : null}
              {profileMessage ? <p className="success">{profileMessage}</p> : null}
              <button type="submit">Save profile</button>
            </form>
          </section>

          <section className="card">
            <h2>Change password</h2>
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
              {passwordError ? <p className="error">{passwordError}</p> : null}
              {passwordMessage ? <p className="success">{passwordMessage}</p> : null}
              <button type="submit">Change password</button>
            </form>
          </section>
        </div>
      </main>
    </ProtectedRoute>
  );
}
