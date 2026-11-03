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

export interface ItemOverlayEntry {
  projectKey: string;
  itemId: string;
}

/**
 * Drawer layers, bottom first. The URL keeps one ``item``/``itemProject``
 * pair per layer so reloading/back-forward restores the same stack.
 */
export function itemOverlayStack(search: string): ItemOverlayEntry[] {
  const params = new URLSearchParams(search);
  const ids = params.getAll("item");
  const projects = params.getAll("itemProject");
  return ids
    .map((itemId, index) => ({
      itemId,
      projectKey: projects[index] ?? projects[0] ?? "",
    }))
    .filter((entry) => entry.itemId && entry.projectKey);
}

function itemOverlayStackSearch(search: string, stack: ItemOverlayEntry[]): string {
  const params = new URLSearchParams(search);
  params.delete("item");
  params.delete("itemProject");
  for (const entry of stack) {
    params.append("item", entry.itemId);
    params.append("itemProject", entry.projectKey);
  }
  return params.toString();
}

/**
 * Open a drawer layer. Re-opening an item already in the stack promotes that
 * layer to the top instead of adding a duplicate (RDM-136).
 */
export function pushItemOverlay(
  search: string,
  stack: ItemOverlayEntry[],
  projectKey: string,
  itemId: string,
): string {
  const next = stack.filter((entry) => entry.itemId !== itemId);
  next.push({ projectKey, itemId });
  return itemOverlayStackSearch(search, next);
}

/** Close the top layer, revealing the one below; empty stack clears the drawer. */
export function popItemOverlay(search: string, stack: ItemOverlayEntry[]): string {
  return itemOverlayStackSearch(search, stack.slice(0, -1));
}

/** Search params that open the in-page work item drawer (single layer). */
export function itemOverlaySearch(
  search: string,
  projectKey: string,
  itemId: string,
): string {
  return itemOverlayStackSearch(search, [{ projectKey, itemId }]);
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
