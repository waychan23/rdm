import React from "react";
import ReactDOM from "react-dom/client";
import { Link, RouterProvider } from "react-router-dom";
import { setGlobalTheme } from "@atlaskit/tokens/set-global-theme";
import "@atlaskit/css-reset";
import type { RouterLinkComponent } from "@atlaskit/app-provider";
import AppProvider from "@atlaskit/app-provider";
import { FlagsProvider } from "@atlaskit/flag/flags-provider";

import "./styles/global.css";
import { router } from "./router";

// Light-only for the rewrite; dark mode is explicit backlog.
setGlobalTheme({ colorMode: "light", light: "light", dark: "dark" });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider routerLinkComponent={Link as unknown as RouterLinkComponent<any>}>
      <FlagsProvider>
        <RouterProvider router={router} />
      </FlagsProvider>
    </AppProvider>
  </React.StrictMode>,
);
