import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { BrasaPointsPage } from "./pages/BrasaPointsPage";
import { HomePage } from "./pages/HomePage";
import { JoinPage } from "./pages/JoinPage";
import { LocationsPage } from "./pages/LocationsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/locations" element={<LocationsPage />} />
        <Route path="/brasa-points" element={<BrasaPointsPage />} />
        <Route path="/join" element={<JoinPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
