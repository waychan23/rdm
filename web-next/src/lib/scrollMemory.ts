// The item overlay is absolutely positioned, so opening it collapses the
// shell's scrollable height and the browser clamps main.scrollTop to 0. Keep
// the list's position and restore it when the overlay closes.
//
// RDM-80 also keeps a position per page pathname (menu switches) and per board
// column, so the three work item pages feel "kept alive" even though React
// Router remounts them.
const MAX_ENTRIES = 12;

const pending = new Map<string, number>();
const positions = new Map<string, number>();
const columnPositions = new Map<string, number>();

function rememberIn(
  store: Map<string, number>,
  key: string,
  value: number,
  max = MAX_ENTRIES,
): void {
  if (value <= 0) return;
  store.delete(key);
  store.set(key, value);
  if (store.size > max) {
    const oldest = store.keys().next().value;
    if (oldest !== undefined) store.delete(oldest);
  }
}

/**
 * The element that scrolls the page's main content. Fixed-height list pages
 * scroll their table body instead of the shell (RDM-125); everything else
 * still scrolls `app-content`.
 */
export function pageScroller(): HTMLElement | null {
  return (
    document.querySelector<HTMLElement>('[data-testid="work-item-table-scroll"]') ??
    document.querySelector<HTMLElement>('[data-testid="app-content"]')
  );
}

export function pageScrollTop(): number {
  return pageScroller()?.scrollTop ?? 0;
}

export function rememberScroll(path: string, top: number): void {
  if (top <= 0) {
    pending.delete(path);
    return;
  }
  rememberIn(pending, path, top);
}

/** Save the current page's position for a later menu switch (RDM-80). */
export function rememberViewPosition(pathname: string, top: number): void {
  rememberIn(positions, pathname, top);
}

/** Board columns keep their own vertical offset (RDM-80). */
export function rememberColumnPosition(key: string, top: number): void {
  rememberIn(columnPositions, key, top);
}

export function readColumnPosition(key: string): number | null {
  return columnPositions.get(key) ?? null;
}

/** Consume the saved offset for this route, if the overlay just closed. */
export function takeScroll(path: string): number | null {
  const top = pending.get(path);
  if (top !== undefined) {
    pending.delete(path);
    return top;
  }
  // Menu switches restore by pathname; filters/pagination do not need to match.
  return positions.get(path.split("?")[0]) ?? null;
}

export function clearScrollMemory(): void {
  pending.clear();
  positions.clear();
  columnPositions.clear();
}
