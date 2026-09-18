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
  ApiError,
  clearSessionAndRedirectToLogin,
  clearToken,
  fetchCurrentUser,
  getStoredToken,
  storeToken,
  toUserFacingMessage,
  type AuthResponse,
  type PublicUser,
  type TokenResponse,
} from "../lib/api";

type AuthContextValue = {
  token: string | null;
  user: PublicUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  sessionError: string | null;
  retrySession: () => void;
  signIn: (authResponse: TokenResponse | AuthResponse) => Promise<void>;
  logout: () => void;
  setUser: (user: PublicUser | null) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<PublicUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionNonce, setSessionNonce] = useState(0);

  useEffect(() => {
    const savedToken = getStoredToken();
    setToken(savedToken);
    if (!savedToken) {
      setUser(null);
      setSessionError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setSessionError(null);

    fetchCurrentUser()
      .then((profile) => {
        if (cancelled) {
          return;
        }
        setUser(profile);
        setSessionError(null);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          clearSessionAndRedirectToLogin();
          setToken(null);
          setUser(null);
          setSessionError(null);
          return;
        }
        setUser(null);
        setSessionError(
          toUserFacingMessage(error, "We could not check your session. Confirm the API is running."),
        );
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [sessionNonce]);

  const retrySession = useCallback(() => {
    setSessionNonce((value) => value + 1);
  }, []);

  const signIn = useCallback(async (authResponse: TokenResponse | AuthResponse) => {
    const accessToken = authResponse?.access_token;
    if (!accessToken) {
      throw new ApiError(toUserFacingMessage(null, "Sign-in did not return a session. Try again."));
    }
    storeToken(accessToken);
    setToken(accessToken);
    setSessionError(null);
    if ("user" in authResponse && authResponse?.user) {
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
      sessionError,
      retrySession,
      signIn,
      logout,
      setUser,
    }),
    [token, user, isLoading, sessionError, retrySession, signIn, logout],
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
