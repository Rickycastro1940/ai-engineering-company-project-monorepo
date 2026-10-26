import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { BackofficeLayout } from "./components/BackofficeLayout";
import { AccessiblePage } from "./pages/AccessiblePage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { IncidentFormPage } from "./pages/IncidentFormPage";
import { IncidentListPage, IncidentSummaryPage } from "./pages/IncidentListPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";
import { RfpIntakePage } from "./pages/RfpIntakePage";
import { WeeklyPerformancePage } from "./pages/WeeklyPerformancePage";

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
            <Route path="/rfp-intake" element={<RfpIntakePage />} />
            <Route path="/incidents/new" element={<IncidentFormPage />} />
            <Route path="/incidents/summary" element={<IncidentSummaryPage />} />
            <Route path="/incidents" element={<IncidentListPage />} />
            <Route path="/reporting/weekly-performance" element={<WeeklyPerformancePage />} />
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
