import {
  lazy,
  Suspense,
  useEffect,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { BACKDROP_INTERACTIVE } from "../lib/itemOverlay";
import { itemPath, originFor } from "../lib/navigation";
import { OriginSearchProvider } from "../lib/originSearch";
import BacklogPage from "./BacklogPage";
import BoardPage from "./BoardPage";
import InboxPage from "./InboxPage";
import MailboxPage from "./MailboxPage";
import SprintsPage from "./SprintsPage";
import ItemPanel from "./item/ItemPanel";
import "../styles/item.css";

// Any page can own the drawer backdrop. The origin URL decides which page is
// rendered behind the drawer instead of always falling back to the backlog.
// Pages not commonly used behind the drawer stay lazy to keep this chunk small.
const ProjectsPage = lazy(() => import("./ProjectsPage"));
const OverviewPage = lazy(() => import("./OverviewPage"));
const SearchPage = lazy(() => import("./SearchPage"));
const ReleasesPage = lazy(() => import("./ReleasesPage"));
const WorkspacesPage = lazy(() => import("./WorkspacesPage"));
const MembersPage = lazy(() => import("./MembersPage"));
const SettingsPage = lazy(() => import("./SettingsPage"));
const PersonalSettingsPage = lazy(() => import("./PersonalSettingsPage"));
const WorkflowConfigsPage = lazy(() => import("./WorkflowConfigsPage"));
const OrgUsersPage = lazy(() => import("./OrgUsersPage"));

interface OriginRoute {
  /** Project key named by the origin route; "" for global pages. */
  projectKey: string | null;
  page: ReactNode;
}

function originRoute(originPath: string): OriginRoute {
  const segments = originPath.split("/").filter(Boolean);

  if (segments[0] === "projects") {
    if (segments.length === 1) return { projectKey: null, page: <ProjectsPage /> };
    const projectKey = decodeURIComponent(segments[1]);
    const page = segments[2];
    switch (page) {
      case undefined:
        return { projectKey, page: <OverviewPage /> };
      case "board":
        return { projectKey, page: <BoardPage /> };
      case "backlog":
        return { projectKey, page: <BacklogPage /> };
      case "issues":
        return { projectKey, page: <BacklogPage /> };
      case "sprints":
        return { projectKey, page: <SprintsPage /> };
      case "releases":
        return { projectKey, page: <ReleasesPage /> };
      case "mailbox":
        return { projectKey, page: <MailboxPage /> };
      case "workspaces":
        return { projectKey, page: <WorkspacesPage /> };
      case "members":
        return { projectKey, page: <MembersPage /> };
      case "settings":
        return { projectKey, page: <SettingsPage /> };
      default:
        // `/projects/:key/items/:id` backdrops are never created in-app; render
        // a blank surface rather than an unrelated list.
        return { projectKey, page: null };
    }
  }

  switch (segments[0]) {
    case "inbox":
      return { projectKey: "", page: <InboxPage /> };
    case "mailbox":
      return { projectKey: "", page: <MailboxPage /> };
    case "search":
      return { projectKey: "", page: <SearchPage /> };
    case "settings":
      return { projectKey: "", page: <PersonalSettingsPage /> };
    case "workflow-configs":
      return { projectKey: "", page: <WorkflowConfigsPage /> };
    case "org":
      return { projectKey: "", page: <OrgUsersPage /> };
    default:
      return { projectKey: null, page: null };
  }
}

// P2 overlay for direct `/items/:id` links: the fallback/origin page stays
// visible behind the detail aside (no scrim, no focus trap) — blank backdrop
// clicks close the panel. In-app navigation uses ItemOverlayHost instead.
export default function ItemPage() {
  const { key: projectKey = "", id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const initialOrigin = originFor(location.state, `/projects/${projectKey}/backlog`);
  // Backdrop pages may change filters or close their detail drawer while the
  // item is open; remember the live origin so closing returns to that state.
  const [origin, setOrigin] = useState(initialOrigin);
  useEffect(() => setOrigin(initialOrigin), [initialOrigin]);
  const background = originRoute(origin.split("?")[0]);

  const closeToOrigin = () => navigate(origin);

  const dismissFromBackdrop = (event: MouseEvent<HTMLDivElement>) => {
    // Interactive targets keep their behaviour; a text-selection drag ending
    // on blank space must not close the panel either.
    const target = event.target;
    if (!(target instanceof Element) || target.closest(BACKDROP_INTERACTIVE)) return;
    if (!window.getSelection()?.isCollapsed) return;
    closeToOrigin();
  };

  return (
    <div className="rdm-item-overlay" data-testid="item-overlay">
      <div
        className="rdm-item-backdrop"
        data-testid="item-backdrop"
        onClick={dismissFromBackdrop}
      >
        {/* The drawer route owns the address bar; the backdrop keeps the page
            URL (filters included) it was opened from. */}
        <OriginSearchProvider
          key={initialOrigin}
          origin={initialOrigin}
          projectKey={background.projectKey}
          onOriginChange={setOrigin}
        >
          <Suspense fallback={null}>{background.page}</Suspense>
        </OriginSearchProvider>
      </div>
      <ItemPanel
        projectKey={projectKey}
        itemId={id}
        onClose={closeToOrigin}
        onOpenItem={(childId) =>
          // Keep the original page as the backdrop when drilling in.
          navigate(itemPath(projectKey, childId), { state: { from: origin } })
        }
      />
    </div>
  );
}
