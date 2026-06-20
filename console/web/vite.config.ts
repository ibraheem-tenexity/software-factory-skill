import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build to console/web/dist; FastAPI serves it when SF_CONSOLE=react. Dev proxies /api + /login
// to the running uvicorn so the SPA talks to the real console in development.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: "index.html",
        admin: "admin.html",
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/login.html": "http://127.0.0.1:8765",
    },
  },
});
