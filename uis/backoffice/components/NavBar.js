"use client";

import Link from "next/link";
import { useAuth } from "./AuthProvider";

export default function NavBar() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <nav className="navbar">
      <Link className="brand" href="/">
        Backoffice
      </Link>
      <div className="nav-actions">
        {isAuthenticated ? (
          <>
            <Link href="/profile">{user?.name || "Profile"}</Link>
            <button type="button" className="link-button" onClick={logout}>
              Logout
            </button>
          </>
        ) : (
          <>
            <Link href="/login">Login</Link>
            <Link href="/register">Register</Link>
          </>
        )}
      </div>
    </nav>
  );
}
