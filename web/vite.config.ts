import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Built to web/dist and served by FastAPI (api/audit_api.py) at "/"; `npm run dev` proxies the API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/v1": "http://127.0.0.1:8000" } },
});
