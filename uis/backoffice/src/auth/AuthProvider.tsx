import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearSessionAndRedirectToLogin,
  clearToken,
  fetchCurrentUser,
  getStoredToken,
  storeToken,
  type AuthResponse,
  type PublicUser,
  type TokenResponse,
} from "../lib/api";

type AuthContextValue = {
  token: string | null;
  user: PublicUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  signIn: (authResponse: TokenResponse | AuthResponse) => Promise<void>;
  logout: () => void;
  setUser: (user: PublicUser | null) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<PublicUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedToken = getStoredToken();
    setToken(savedToken);
    if (!savedToken) {
      setIsLoading(false);
      return;
    }

    fetchCurrentUser()
      .then(setUser)
      .catch(() => {
        clearSessionAndRedirectToLogin();
        setToken(null);
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const signIn = useCallback(async (authResponse: TokenResponse | AuthResponse) => {
    storeToken(authResponse.access_token);
    setToken(authResponse.access_token);
    if ("user" in authResponse && authResponse.user) {
      setUser(authResponse.user);
      return;
    }
    try {
      const profile = await fetchCurrentUser();
      setUser(profile);
    } catch (error) {
      clearSessionAndRedirectToLogin();
      setToken(null);
      setUser(null);
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    window.location.replace("/login");
  }, []);

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated: Boolean(token && user),
      isLoading,
      signIn,
      logout,
      setUser,
    }),
    [token, user, isLoading, signIn, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
