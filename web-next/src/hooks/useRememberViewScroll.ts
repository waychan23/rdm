import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { useListOrigin } from "../lib/originSearch";
import { rememberViewPosition } from "../lib/scrollMemory";

/**
 * Keep the shell scroll offset per page pathname so returning from another
 * menu item restores the previous position (RDM-80). The item-drawer backdrop
 * is skipped: it has its own explicit save/restore and must not overwrite the
 * list's position while the overlay collapses the scroll height.
 */
export function useRememberViewScroll(): void {
  const location = useLocation();
  const listOrigin = useListOrigin();
  const active = listOrigin === null;
  const pathname = location.pathname;

  useEffect(() => {
    if (!active) return;
    const content = document.querySelector<HTMLElement>('[data-testid="app-content"]');
    if (!content) return;
    let frame = 0;
    const onScroll = () => {
      if (frame !== 0) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        rememberViewPosition(pathname, content.scrollTop);
      });
    };
    content.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      content.removeEventListener("scroll", onScroll);
      if (frame !== 0) cancelAnimationFrame(frame);
    };
  }, [active, pathname]);
}
