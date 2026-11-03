import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Release builds get their version from CI. Local builds say "dev".
  define: { __APP_VERSION__: JSON.stringify(process.env.APP_VERSION || "dev") },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
