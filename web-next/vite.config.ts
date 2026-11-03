import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import compiled from "@compiled/vite-plugin";
import react from "@vitejs/plugin-react";

// The Web UI is a standalone frontend (architecture §17.160). In dev the Vite
// server proxies the API namespaces to rdm serve; in production nginx serves
// `web-next/dist` and proxies the same paths. `RDM_API_URL` lets the Playwright
// setup point the proxy at its throwaway backend.
const API_TARGET = process.env.RDM_API_URL ?? "http://127.0.0.1:8765";

// Legacy root OAuth paths are still proxied so Python can 308 them to
// /api/oauth/*; without this the SPA fallback would swallow them.
const proxy = {
  "/api": API_TARGET,
  "/.well-known": API_TARGET,
  "/mcp": { target: API_TARGET, ws: true },
  "/authorize": API_TARGET,
  "/token": API_TARGET,
  "/register": API_TARGET,
  "/revoke": API_TARGET,
};

export default defineConfig({
  // Compiled must run before the React plugin (pre-ordering is enforced by the
  // plugin). It compiles @atlaskit/css `cssMap` styles at build time; without it
  // the runtime throws "Code was executed when it shouldn't have".
  //
  // Keep extraction off (default). Note that stylesheet order is still not
  // reliable for borders: primitives' Box ships `border: none`, so card borders
  // go through the inline `cardBorder` helper (components/cardBorder.ts).
  plugins: [compiled({ importReact: false }), react()],
  build: {
    // Default `dist` under web-next/. The bundle no longer ships inside the
    // Python wheel; deploy it to nginx.
  },
  resolve: {
    // pnpm + Atlaskit transitive deps must resolve a single React copy. The
    // Compiled runtime must also be a single copy for class-name parity.
    dedupe: ["react", "react-dom", "@compiled/react"],
    alias: {
      // pdf.js requires this from its Node-only canvas factory; the real
      // package has a native binding that cannot be bundled for the browser.
      "@napi-rs/canvas": fileURLToPath(new URL("./src/lib/nodeOnlyCanvas.ts", import.meta.url)),
    },
  },
  server: {
    strictPort: true,
    proxy,
  },
  // `vite preview` exercises the production bundle + the same proxy topology
  // as nginx; the web e2e suite runs against it.
  preview: {
    proxy,
  },
});
