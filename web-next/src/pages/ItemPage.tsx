import { useNavigate, useParams } from "react-router-dom";

import BacklogPage from "./BacklogPage";
import ItemPanel from "./item/ItemPanel";
import "../styles/item.css";

// P2 overlay: the list stays visible and usable behind the detail aside
// (no scrim, no focus trap) — matching the legacy Vue interaction.
export default function ItemPage() {
  const { key: projectKey = "", id = "" } = useParams();
  const navigate = useNavigate();

  return (
    <div className="rdm-item-overlay">
      <div className="rdm-item-backdrop">
        <BacklogPage />
      </div>
      <ItemPanel
        projectKey={projectKey}
        itemId={id}
        onClose={() => navigate(`/projects/${projectKey}/backlog`)}
        onOpenItem={(childId) => navigate(`/projects/${projectKey}/items/${childId}`)}
      />
    </div>
  );
}
