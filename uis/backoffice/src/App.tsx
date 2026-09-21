import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { BackofficeLayout } from "./components/BackofficeLayout";
import { AccessiblePage } from "./pages/AccessiblePage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { InventoryPage } from "./pages/InventoryPage";
import { InventoryOrderPage } from "./pages/InventoryOrderPage";
import { InboundOrderPage } from "./pages/InboundOrderPage";
import { LoginPage } from "./pages/LoginPage";
import { ProductsPage } from "./pages/ProductsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";

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
            <Route path="/inventory/orders/new" element={<InventoryOrderPage />} />
            <Route path="/backoffice/inventory/products" element={<Navigate to="/inventory/products" replace />} />
            <Route path="/backoffice/inventory/orders/inbound" element={<Navigate to="/inventory/orders/inbound" replace />} />
            <Route path="/inventory" element={<InventoryPage />} />
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
