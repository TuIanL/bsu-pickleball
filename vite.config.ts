import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { localApiProxy } from "./scripts/local-api-proxy";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  if (env.VITE_PICKLEBALL_API_TOKEN) {
    throw new Error("Remove VITE_PICKLEBALL_API_TOKEN; use server-only PICKLEBALL_API_TOKEN.");
  }
  const proxy = localApiProxy(env);
  return {
    plugins: [react(), tailwindcss(), proxy.plugin],
    server: { host: "127.0.0.1", proxy: proxy.routes },
    preview: { host: "127.0.0.1", proxy: proxy.routes },
    build: { manifest: true },
    test: { environment: "jsdom" },
  };
});
