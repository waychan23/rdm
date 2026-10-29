import { useLocation, useNavigate, useParams } from "react-router-dom";

import { itemPath, originFor } from "../lib/navigation";
import BacklogPage from "./BacklogPage";
import BoardPage from "./BoardPage";
import SprintsPage from "./SprintsPage";
import ItemPanel from "./item/ItemPanel";
import "../styles/item.css";

// P2 overlay: the list stays visible and usable behind the detail aside
// (no scrim, no focus trap) — matching the legacy Vue interaction.
export default function ItemPage() {
  const { key: projectKey = "", id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const origin = originFor(location.state, `/projects/${projectKey}/backlog`);

  const backdrop = origin.includes("/board")
    ? <BoardPage />
    : origin.includes("/sprints")
      ? <SprintsPage />
      : <BacklogPage />;

  return (
    <div className="rdm-item-overlay" data-testid="item-overlay">
      <div className="rdm-item-backdrop" data-testid="item-backdrop">
        {backdrop}
      </div>
      <ItemPanel
        projectKey={projectKey}
        itemId={id}
        onClose={() => navigate(origin)}
        onOpenItem={(childId) =>
          navigate(itemPath(projectKey, childId), {
            state: { from: location.pathname + location.search },
          })
        }
      />
    </div>
  );
}
