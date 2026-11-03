import { useLayoutEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { takeScroll, pageScroller } from "../lib/scrollMemory";

/**
 * Restore the list's scroll offset after the work-item overlay closes or after
 * a menu switch (RDM-80). Fixed-height list pages keep the offset on their own
 * table scroller (RDM-125). Runs once per mount so filter/page changes do not
 * pull the viewport back to a previous position.
 *
 * Layout effect so the restored position is in place before the browser paints
 * (the page snapshot renders its rows on the first commit).
 */
export function useRestoreScroll(): void {
  const location = useLocation();
  const path = location.pathname + location.search;
  const restored = useRef(false);
  useLayoutEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const top = takeScroll(path);
    if (top === null) return;
    const content = pageScroller();
    if (content) content.scrollTop = top;
  }, [path]);
}
