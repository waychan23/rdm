import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Dev server proxies API/MCP to rdm serve; production build lands in the
// package resource dir and is served by RootDispatch (architecture §16.37).
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: "../src/rdm/resources/web-dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/authorize": "http://127.0.0.1:8765",
      "/token": "http://127.0.0.1:8765",
      "/register": "http://127.0.0.1:8765",
      "/revoke": "http://127.0.0.1:8765",
      "/.well-known": "http://127.0.0.1:8765",
      "/mcp": {
        target: "http://127.0.0.1:8765",
        ws: true,
      },
    },
  },
});
