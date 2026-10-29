import { defineConfig } from "vite";
import compiled from "@compiled/vite-plugin";
import react from "@vitejs/plugin-react";

// Dev server proxies API/MCP/OAuth to rdm serve; the production build lands in
// the package resource dir and is served by RootDispatch (architecture §16.62).
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
    outDir: "../src/rdm/resources/web-next-dist",
    emptyOutDir: true,
  },
  resolve: {
    // pnpm + Atlaskit transitive deps must resolve a single React copy. The
    // Compiled runtime must also be a single copy for class-name parity.
    dedupe: ["react", "react-dom", "@compiled/react"],
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
