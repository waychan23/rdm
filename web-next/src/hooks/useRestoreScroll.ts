import { useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";

import { takeScroll } from "../lib/scrollMemory";

/**
 * Restore the list's shell scroll offset after the work-item overlay closes.
 * Layout effect so the restored position is in place before the browser paints
 * (the page snapshot renders its rows on the first commit).
 */
export function useRestoreScroll(): void {
  const location = useLocation();
  const path = location.pathname + location.search;
  useLayoutEffect(() => {
    const top = takeScroll(path);
    if (top === null) return;
    const content = document.querySelector<HTMLElement>('[data-testid="app-content"]');
    if (content) content.scrollTop = top;
  }, [path]);
}
