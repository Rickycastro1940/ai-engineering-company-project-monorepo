"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiRequest, clearToken, getStoredToken, storeToken } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const router = useRouter();
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedToken = getStoredToken();
    setToken(savedToken);
    if (!savedToken) {
      setIsLoading(false);
      return;
    }

    apiRequest("/auth/me")
      .then(setUser)
      .catch(() => {
        clearToken();
        setToken(null);
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const signIn = (authResponse) => {
    storeToken(authResponse.token);
    setToken(authResponse.token);
    setUser(authResponse.user);
  };

  const refreshUser = async () => {
    const profile = await apiRequest("/auth/me");
    setUser(profile);
    return profile;
  };

  const logout = () => {
    clearToken();
    setToken(null);
    setUser(null);
    router.replace("/login");
  };

  const value = useMemo(
    () => ({ token, user, isAuthenticated: Boolean(token), isLoading, signIn, logout, refreshUser, setUser }),
    [token, user, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
