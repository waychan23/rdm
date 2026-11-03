import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { useListOrigin } from "../lib/originSearch";
import { pageScroller, rememberViewPosition } from "../lib/scrollMemory";

/**
 * Keep the page's scroll offset per page pathname so returning from another
 * menu item restores the previous position (RDM-80). The item-drawer backdrop
 * is skipped: it has its own explicit save/restore and must not overwrite the
 * list's position while the overlay collapses the scroll height.
 *
 * Scroll events do not bubble, so listen in the capture phase and only react
 * to the page's current scroller (the table body on fixed-height list pages,
 * `app-content` elsewhere; RDM-125).
 */
export function useRememberViewScroll(): void {
  const location = useLocation();
  const listOrigin = useListOrigin();
  const active = listOrigin === null;
  const pathname = location.pathname;

  useEffect(() => {
    if (!active) return;
    let frame = 0;
    let last: HTMLElement | null = null;
    const onScroll = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || target !== pageScroller()) return;
      last = target;
      if (frame !== 0) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (last) rememberViewPosition(pathname, last.scrollTop);
      });
    };
    document.addEventListener("scroll", onScroll, { capture: true, passive: true });
    return () => {
      document.removeEventListener("scroll", onScroll, true);
      if (frame !== 0) cancelAnimationFrame(frame);
    };
  }, [active, pathname]);
}
