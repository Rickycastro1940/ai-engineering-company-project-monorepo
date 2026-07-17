import { defineConfig } from "vite";

export default defineConfig({
  envPrefix: ["NEXT_PUBLIC_", "VITE_"],
  server: {
    port: 5173,
    proxy: {
      "/telemetry": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
