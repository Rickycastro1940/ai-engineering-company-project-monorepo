import { Navigate } from "react-router-dom";
import { useRequireAuth } from "./useRequireAuth";

/** Layout guard around staff views: missing or invalid JWT → `/login`. */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { shouldRedirectToLogin, isLoading, loginPath } = useRequireAuth();

  if (shouldRedirectToLogin) {
    return <Navigate to={loginPath} replace />;
  }

  if (isLoading) {
    return (
      <section className="auth-card" aria-busy="true">
        <p>Checking your session…</p>
      </section>
    );
  }

  return children;
}
