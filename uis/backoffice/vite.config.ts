import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

// Internal app — separate from uis/website. Proxy API to FastAPI.
// Course env name NEXT_PUBLIC_INVENTORY_API_URL is loaded from .env.local (Vite, not Next.js).
export default defineConfig({
  plugins: [react()],
  envPrefix: ["VITE_", "NEXT_PUBLIC_"],
  server: {
    port: 5174,
    proxy: {
      "/locations": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/inventory": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/auth": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/users": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/profiles": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
