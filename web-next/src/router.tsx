import { lazy, Suspense, type ReactNode } from "react";
import type { LoaderFunctionArgs } from "react-router-dom";
import { Navigate, createBrowserRouter, redirect } from "react-router-dom";

import Spinner from "@atlaskit/spinner";
import { Box } from "@atlaskit/primitives/compiled";

import { ensureSession } from "./lib/auth";
import AppShell from "./shell/AppShell";
import LoginPage from "./pages/LoginPage";

// Route-level code splitting (the old single chunk was >1MB; Batch 6).
const AuthCallbackPage = lazy(() => import("./pages/AuthCallbackPage"));
const SetPasswordPage = lazy(() => import("./pages/SetPasswordPage"));
const ConsentPage = lazy(() => import("./pages/ConsentPage"));
const ProjectsPage = lazy(() => import("./pages/ProjectsPage"));
const InboxPage = lazy(() => import("./pages/InboxPage"));
const SearchPage = lazy(() => import("./pages/SearchPage"));
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const BoardPage = lazy(() => import("./pages/BoardPage"));
const BacklogPage = lazy(() => import("./pages/BacklogPage"));
const SprintsPage = lazy(() => import("./pages/SprintsPage"));
const ReleasesPage = lazy(() => import("./pages/ReleasesPage"));
const MailboxPage = lazy(() => import("./pages/MailboxPage"));
const WorkspacesPage = lazy(() => import("./pages/WorkspacesPage"));
const MembersPage = lazy(() => import("./pages/MembersPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const OrgUsersPage = lazy(() => import("./pages/OrgUsersPage"));
const PersonalSettingsPage = lazy(() => import("./pages/PersonalSettingsPage"));
const ItemPage = lazy(() => import("./pages/ItemPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

async function requireAuth({ request }: LoaderFunctionArgs) {
  const user = await ensureSession();
  if (!user) {
    const url = new URL(request.url);
    return redirect(`/login?redirect=${encodeURIComponent(url.pathname + url.search)}`);
  }
  return null;
}

/** Org users is only for org owners / user managers; direct URLs must bounce. */
async function requireOrgAdmin() {
  const user = await ensureSession();
  const allowed =
    !!user &&
    (user.org_roles.includes("org_owner") || user.org_roles.includes("user_manager"));
  return allowed ? null : redirect("/projects");
}

function withSuspense(node: ReactNode) {
  return (
    <Suspense
      fallback={
        <Box padding="space.400" style={{ display: "flex", justifyContent: "center" }}>
          <Spinner size="large" />
        </Box>
      }
    >
      {node}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  { path: "/login", Component: LoginPage },
  { path: "/auth/callback", Component: () => withSuspense(<AuthCallbackPage />) },
  { path: "/set-password", Component: () => withSuspense(<SetPasswordPage />) },
  // Consent is key-authenticated (no Bearer/session) and renders bare (§17).
  { path: "/oauth/consent/:id", Component: () => withSuspense(<ConsentPage />) },
  {
    Component: AppShell,
    loader: requireAuth,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: "projects", Component: () => withSuspense(<ProjectsPage />) },
      { path: "inbox", Component: () => withSuspense(<InboxPage />) },
      { path: "mailbox", Component: () => withSuspense(<MailboxPage />) },
      { path: "search", Component: () => withSuspense(<SearchPage />) },
      { path: "projects/:key", Component: () => withSuspense(<OverviewPage />) },
      { path: "projects/:key/board", Component: () => withSuspense(<BoardPage />) },
      { path: "projects/:key/backlog", Component: () => withSuspense(<BacklogPage />) },
      { path: "projects/:key/issues", Component: () => withSuspense(<BacklogPage />) },
      { path: "projects/:key/sprints", Component: () => withSuspense(<SprintsPage />) },
      { path: "projects/:key/releases", Component: () => withSuspense(<ReleasesPage />) },
      { path: "projects/:key/mailbox", Component: () => withSuspense(<MailboxPage />) },
      {
        path: "projects/:key/workspaces",
        Component: () => withSuspense(<WorkspacesPage />),
      },
      { path: "projects/:key/members", Component: () => withSuspense(<MembersPage />) },
      { path: "projects/:key/settings", Component: () => withSuspense(<SettingsPage />) },
      { path: "projects/:key/items/:id", Component: () => withSuspense(<ItemPage />) },
      { path: "org/users", loader: requireOrgAdmin, Component: () => withSuspense(<OrgUsersPage />) },
      { path: "settings", Component: () => withSuspense(<PersonalSettingsPage />) },
      { path: "*", Component: () => withSuspense(<NotFoundPage />) },
    ],
  },
]);
