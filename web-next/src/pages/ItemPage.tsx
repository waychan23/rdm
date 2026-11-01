import type { MouseEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { itemPath, originFor } from "../lib/navigation";
import { OriginSearchProvider } from "../lib/originSearch";
import BacklogPage from "./BacklogPage";
import BoardPage from "./BoardPage";
import SprintsPage from "./SprintsPage";
import ItemPanel from "./item/ItemPanel";
import "../styles/item.css";

// Anything the backdrop needs to keep handling itself: rows/cards open
// another item, controls keep their own click behaviour. Clicking the blank
// area between/behind them dismisses the panel instead.
const BACKDROP_INTERACTIVE =
  "a, button, input, select, textarea, label, tr, thead, [contenteditable='true'], " +
  "[role='button'], [role='link'], [role='checkbox'], [role='radio'], " +
  "[role='combobox'], [role='menuitem'], [role='option'], [role='tab'], " +
  "[role='dialog'], [data-testid='sprint-detail-drawer'], " +
  // Page chrome around the list/board (headings, filters) is not "blank".
  "[data-testid='backlog-header'], [data-testid='work-item-filters'], " +
  "[data-testid='board-header'], [data-testid='board-kind-filter'], " +
  "[data-testid='sprints-header']";

// P2 overlay: the list stays visible and usable behind the detail aside
// (no scrim, no focus trap) — blank backdrop clicks close the panel.
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

  const dismissFromBackdrop = (event: MouseEvent<HTMLDivElement>) => {
    // Interactive targets keep their behaviour; a text-selection drag ending
    // on blank space must not close the panel either.
    const target = event.target;
    if (!(target instanceof Element) || target.closest(BACKDROP_INTERACTIVE)) return;
    if (!window.getSelection()?.isCollapsed) return;
    navigate(origin);
  };

  return (
    <div className="rdm-item-overlay" data-testid="item-overlay">
      <div
        className="rdm-item-backdrop"
        data-testid="item-backdrop"
        onClick={dismissFromBackdrop}
      >
        {/* The drawer route owns the address bar; the backdrop keeps the list
            URL (filters included) it was opened from. */}
        <OriginSearchProvider origin={origin}>{backdrop}</OriginSearchProvider>
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
