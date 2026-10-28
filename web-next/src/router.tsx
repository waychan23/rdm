import type { LoaderFunctionArgs } from "react-router-dom";
import { Navigate, createBrowserRouter, redirect } from "react-router-dom";

import { ensureSession } from "./lib/auth";
import AppShell from "./shell/AppShell";
import BacklogPage from "./pages/BacklogPage";
import BoardPage from "./pages/BoardPage";
import ConsentPage from "./pages/ConsentPage";
import ItemPage from "./pages/ItemPage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import OverviewPage from "./pages/OverviewPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import ProjectsPage from "./pages/ProjectsPage";

async function requireAuth({ request }: LoaderFunctionArgs) {
  const member = await ensureSession();
  if (!member) {
    const url = new URL(request.url);
    return redirect(`/login?redirect=${encodeURIComponent(url.pathname + url.search)}`);
  }
  return null;
}

const placeholder = (title: string) => <PlaceholderPage title={title} />;

export const router = createBrowserRouter([
  { path: "/login", Component: LoginPage },
  // Consent needs a session but renders without the app shell ("bare").
  { path: "/oauth/consent/:id", Component: ConsentPage, loader: requireAuth },
  {
    Component: AppShell,
    loader: requireAuth,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: "projects", Component: ProjectsPage },
      { path: "projects/:key", Component: OverviewPage },
      { path: "projects/:key/board", Component: BoardPage },
      { path: "projects/:key/backlog", Component: BacklogPage },
      { path: "projects/:key/sprints", element: placeholder("迭代") },
      { path: "projects/:key/mailbox", element: placeholder("信箱") },
      { path: "projects/:key/workspaces", element: placeholder("工作区") },
      { path: "projects/:key/members", element: placeholder("成员") },
      { path: "projects/:key/settings", element: placeholder("设置") },
      { path: "projects/:key/items/:id", Component: ItemPage },
      { path: "*", Component: NotFoundPage },
    ],
  },
]);
