import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import ItemPanel from "../pages/item/ItemPanel";
import {
  BACKDROP_INTERACTIVE,
  itemOverlayStack,
  popItemOverlay,
  pushItemOverlay,
} from "../lib/itemOverlay";
import {
  nextItemOverlayHostId,
  useItemOverlayHost,
} from "../lib/itemOverlayVisibility";
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
 *
 * Opening an item from inside a panel pushes a new layer (RDM-136); layers
 * stay mounted so going back restores the previous panel instantly. A repeat
 * open of an item already in the stack promotes that layer to the top.
 */
export default function ItemOverlayHost() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  // Direct `/items/:id` links keep using the route-backed overlay.
  const onLegacyRoute = location.pathname.includes("/items/");
  const search = params.toString();
  const stack = useMemo(
    () => (onLegacyRoute ? [] : itemOverlayStack(search)),
    [onLegacyRoute, search],
  );
  const open = stack.length > 0;
  const [hostId] = useState(nextItemOverlayHostId);
  // List pages keep update events queued while any layer covers them (RDM-150).
  useItemOverlayHost(hostId, stack.length);

  const close = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("item");
    next.delete("itemProject");
    setParams(next, { replace: true });
  }, [params, setParams]);

  const goBack = useCallback(() => {
    setParams(new URLSearchParams(popItemOverlay(params.toString(), stack)), {
      replace: true,
    });
  }, [params, setParams, stack]);

  const openItem = (nextId: string) => {
    const current = stack[stack.length - 1];
    if (!current) return;
    setParams(
      new URLSearchParams(
        pushItemOverlay(params.toString(), stack, current.projectKey, nextId),
      ),
    );
  };

  useEffect(() => {
    if (!open) return;
    // Dismiss only on a complete click on blank space (RDM-159): a gesture that
    // starts inside the panel and ends outside (text selection dragged across
    // the edge) still dispatches `click` on the common ancestor, which must not
    // close the drawer. Track both ends of the gesture instead of trusting the
    // synthetic click target, which lies for cross-boundary drags.
    const isBlank = (event: MouseEvent) => {
      if (clickPathMatches(event, '[data-testid="item-panel"]')) return false;
      if (clickPathMatches(event, BACKDROP_INTERACTIVE)) return false;
      return true;
    };
    let startedBlank = false;
    let endedBlank = false;
    const onPointerDown = (event: PointerEvent) => {
      startedBlank = isBlank(event);
      endedBlank = false;
    };
    const onPointerUp = (event: PointerEvent) => {
      endedBlank = isBlank(event);
    };
    const onClick = (event: MouseEvent) => {
      const blankClick = startedBlank && endedBlank && isBlank(event);
      startedBlank = false;
      endedBlank = false;
      if (!blankClick) return;
      if (!window.getSelection()?.isCollapsed) return;
      close();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointerup", onPointerUp, true);
    // Bubble phase so list rows/navigation run first.
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("pointerup", onPointerUp, true);
      document.removeEventListener("click", onClick);
    };
  }, [open, close]);

  if (!open) return null;
  return (
    <div
      className="rdm-item-overlay rdm-item-overlay--floating"
      data-testid="item-overlay"
    >
      {stack.map((entry, index) => {
        const isTop = index === stack.length - 1;
        return (
          <ItemPanel
            key={`${entry.projectKey}:${entry.itemId}`}
            projectKey={entry.projectKey}
            itemId={entry.itemId}
            onClose={close}
            onOpenItem={openItem}
            onBack={isTop && stack.length > 1 ? goBack : undefined}
            covered={!isTop}
          />
        );
      })}
    </div>
  );
}
