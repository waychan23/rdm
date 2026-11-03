import { useCallback, useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import ItemPanel from "../pages/item/ItemPanel";
import { BACKDROP_INTERACTIVE, itemOverlaySearch } from "../lib/itemOverlay";
import "../styles/item.css";

/**
 * Whether the click landed inside one of `selector`'s matches. Uses the path
 * captured when the event was dispatched because `event.target` may already be
 * detached by the time this listener runs: inline fields swap their read view
 * for the editor during the same click, and `closest()` on a detached node
 * finds no ancestors (RDM-132/RDM-135).
 */
function clickPathMatches(event: MouseEvent, selector: string): boolean {
  return event
    .composedPath()
    .some((node) => node instanceof Element && node.matches(selector));
}

/**
 * In-page work item drawer. It lives beside the current page (AppShell) so
 * opening/closing it never unmounts the page, its filters or an open
 * sprint/release detail drawer.
 */
export default function ItemOverlayHost() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const itemId = params.get("item");
  const projectKey = params.get("itemProject") ?? "";
  // Direct `/items/:id` links keep using the route-backed overlay.
  const onLegacyRoute = location.pathname.includes("/items/");
  const open = Boolean(itemId && projectKey) && !onLegacyRoute;

  const close = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("item");
    next.delete("itemProject");
    setParams(next, { replace: true });
  }, [params, setParams]);

  const openItem = (nextId: string) => {
    setParams(new URLSearchParams(itemOverlaySearch(params.toString(), projectKey, nextId)));
  };

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (clickPathMatches(event, '[data-testid="item-panel"]')) return;
      if (clickPathMatches(event, BACKDROP_INTERACTIVE)) return;
      if (!window.getSelection()?.isCollapsed) return;
      close();
    };
    // Bubble phase so list rows/navigation run first.
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open, close]);

  if (!open || !itemId) return null;
  return (
    <div
      className="rdm-item-overlay rdm-item-overlay--floating"
      data-testid="item-overlay"
    >
      <ItemPanel
        projectKey={projectKey}
        itemId={itemId}
        onClose={close}
        onOpenItem={openItem}
      />
    </div>
  );
}
