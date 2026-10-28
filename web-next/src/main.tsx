import React from "react";
import ReactDOM from "react-dom/client";
import { Link, RouterProvider, createBrowserRouter } from "react-router-dom";
import type { RouterLinkComponent } from "@atlaskit/app-provider";
import { setGlobalTheme } from "@atlaskit/tokens/set-global-theme";
import "@atlaskit/css-reset";
import AppProvider from "@atlaskit/app-provider";
import { FlagsProvider } from "@atlaskit/flag/flags-provider";

import "./styles/global.css";
import HomePage from "./pages/HomePage";

// Light-only for the rewrite; dark mode is explicit backlog.
setGlobalTheme({ colorMode: "light", light: "light", dark: "dark" });

// Batch 0 spike: a single route proves the ADS + Vite toolchain end to end.
// Batches 1-6 replace this with the full route table.
const router = createBrowserRouter([
  { path: "/", element: <HomePage /> },
  { path: "*", element: <HomePage /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider routerLinkComponent={Link as unknown as RouterLinkComponent<any>}>
      <FlagsProvider>
        <RouterProvider router={router} />
      </FlagsProvider>
    </AppProvider>
  </React.StrictMode>,
);
