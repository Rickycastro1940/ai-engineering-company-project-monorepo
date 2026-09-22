import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { BackofficeLayout } from "./components/BackofficeLayout";
import { AccessiblePage } from "./views/AccessiblePage";
import { ChangePasswordPage } from "./views/ChangePasswordPage";
import { LoginPage } from "./views/LoginPage";
import { ProfilePage } from "./views/ProfilePage";
import { RegisterPage } from "./views/RegisterPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            element={
              <ProtectedRoute>
                <BackofficeLayout />
              </ProtectedRoute>
            }
          >
            {/* Staff views: session required (token in localStorage, validated with GET /auth/me). */}
            <Route path="/accessible" element={<AccessiblePage />} />
            <Route path="/account/profile" element={<ProfilePage />} />
            <Route path="/account/change-password" element={<ChangePasswordPage />} />
            <Route path="/" element={<Navigate to="/accessible" replace />} />
            <Route path="*" element={<Navigate to="/accessible" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
