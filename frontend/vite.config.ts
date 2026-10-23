import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the API is proxied, so the browser only ever talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.VITE_DEV_API ?? "http://127.0.0.1:8000" },
  },
  preview: {
    proxy: { "/api": process.env.VITE_DEV_API ?? "http://127.0.0.1:8000" },
  },
});
