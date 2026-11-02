import { useLocation, useNavigate } from "react-router-dom";

import { itemPath } from "./navigation";
import { useListOrigin } from "./originSearch";

// Controls that keep their own click behaviour while the item drawer is open.
// A click on blank space elsewhere dismisses the drawer instead.
export const BACKDROP_INTERACTIVE =
  "a, button, input, select, textarea, label, tr, thead, [contenteditable='true'], " +
  "[role='button'], [role='link'], [role='checkbox'], [role='radio'], " +
  "[role='combobox'], [role='menuitem'], [role='option'], [role='tab'], " +
  "[role='dialog'], [data-testid='sprint-detail-drawer'], " +
  "[data-testid='release-detail-drawer'], " +
  // Page chrome around the list/board (headings, filters) is not "blank".
  "[data-testid='backlog-header'], [data-testid='work-item-filters'], " +
  "[data-testid='board-header'], [data-testid='sprints-header']";

/** Search params that open the in-page work item drawer. */
export function itemOverlaySearch(
  search: string,
  projectKey: string,
  itemId: string,
): string {
  const params = new URLSearchParams(search);
  params.set("item", itemId);
  params.set("itemProject", projectKey);
  return params.toString();
}

/**
 * Open the work item drawer without leaving the current page, so the page and
 * any open detail drawer stay mounted (no remount animation or flash).
 * Legacy `/items/:id` backdrops keep the route-based behaviour.
 */
export function useOpenWorkItem(): (projectKey: string, itemId: string) => void {
  const navigate = useNavigate();
  const location = useLocation();
  const listOrigin = useListOrigin();
  return (projectKey: string, itemId: string) => {
    if (listOrigin) {
      navigate(itemPath(projectKey, itemId), { state: { from: listOrigin } });
      return;
    }
    navigate({
      pathname: location.pathname,
      search: itemOverlaySearch(location.search, projectKey, itemId),
    });
  };
}
