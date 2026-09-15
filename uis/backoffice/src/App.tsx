import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { BackofficeLayout } from "./components/BackofficeLayout";
import { AccessiblePage } from "./pages/AccessiblePage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<BackofficeLayout />}>
          <Route path="/accessible" element={<AccessiblePage />} />
          <Route path="/" element={<Navigate to="/accessible" replace />} />
          <Route path="*" element={<Navigate to="/accessible" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
