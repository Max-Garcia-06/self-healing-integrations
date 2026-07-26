import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend dev server proxies the backend API so the browser can use same-origin
// relative URLs (/api/...). Point at the FastAPI app on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
