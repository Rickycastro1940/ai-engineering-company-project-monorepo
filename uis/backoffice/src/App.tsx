import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { BackofficeLayout } from "./components/BackofficeLayout";
import { AccessiblePage } from "./pages/AccessiblePage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { InboundOrderPage } from "./pages/InboundOrderPage";
import { LoginPage } from "./pages/LoginPage";
import { OrdersPage } from "./pages/OrdersPage";
import { OutboundOrderPage } from "./pages/OutboundOrderPage";
import { ProductsPage } from "./pages/ProductsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";
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
            <Route path="/inventory/products" element={<ProductsPage />} />
            <Route path="/inventory/orders/inbound" element={<InboundOrderPage />} />
            <Route path="/inventory/orders/outbound" element={<OutboundOrderPage />} />
            <Route path="/inventory/orders" element={<OrdersPage />} />
            <Route path="/inventory" element={<Navigate to="/inventory/products" replace />} />
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
