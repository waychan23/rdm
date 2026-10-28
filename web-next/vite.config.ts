import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API/MCP/OAuth to rdm serve; the production build lands in
// the package resource dir and is served by RootDispatch (architecture §16.62).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/rdm/resources/web-next-dist",
    emptyOutDir: true,
  },
  resolve: {
    // pnpm + Atlaskit transitive deps must resolve a single React copy.
    dedupe: ["react", "react-dom"],
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
