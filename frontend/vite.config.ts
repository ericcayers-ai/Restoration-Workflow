import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The frontend never assumes it's bundled in Tauri (ARCHITECTURE.md section 1)
// — in dev it talks to a separately-running `restore serve` over this proxy;
// in production the same build is served *by* that backend, same-origin, so
// no proxy exists there at all. `restore serve` defaults to port 8765; override
// with VITE_BACKEND_PORT if you started it elsewhere.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = `http://127.0.0.1:${env.VITE_BACKEND_PORT || "8765"}`;

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: backend,
          ws: true,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
    },
  };
});
