import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

function proxyApiUnlessSpaDocument() {
  return {
    target: apiTarget,
    changeOrigin: true,
    bypass(req: { method?: string; headers: { accept?: string } }) {
      const method = (req.method ?? "GET").toUpperCase();
      if (method !== "GET" && method !== "HEAD") {
        return undefined;
      }
      const accept = req.headers.accept ?? "";
      // Browser document navigations (e.g. /inventory/products) must hit the Vite SPA.
      // fetch() from src/lib/inventory.ts uses */* or application/json and still proxies.
      if (accept.includes("text/html")) {
        return "/index.html";
      }
      return undefined;
    },
  };
}

// Internal app — separate from uis/website. Proxy API to FastAPI.
// Course env name NEXT_PUBLIC_INVENTORY_API_URL is loaded from .env.local (Vite, not Next.js).
export default defineConfig({
  plugins: [react()],
  envPrefix: ["VITE_", "NEXT_PUBLIC_"],
  server: {
    port: 5174,
    proxy: {
      "/locations": proxyApiUnlessSpaDocument(),
      "/inventory": proxyApiUnlessSpaDocument(),
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
