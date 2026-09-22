import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const apiTarget = process.env.API_PROXY ?? process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";
// Compose sets API_PROXY=http://backend:8000 so the ui container reaches FastAPI by service name.

const proxied = [
  "/locations",
  "/menus",
  "/sales",
  "/customers",
  "/suppliers",
  "/inventory",
  "/auth",
  "/users",
  "/profiles",
  "/api",
];

const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: dir,
  async rewrites() {
    return proxied.flatMap((path) => [
      { source: path, destination: `${apiTarget}${path}` },
      { source: `${path}/:path*`, destination: `${apiTarget}${path}/:path*` },
    ]);
  },
};

export default nextConfig;
