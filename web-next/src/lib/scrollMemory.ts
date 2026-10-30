// The item overlay is absolutely positioned, so opening it collapses the
// shell's scrollable height and the browser clamps main.scrollTop to 0. Keep
// the list's position and restore it when the overlay closes.
const MAX_ENTRIES = 12;
const pending = new Map<string, number>();

export function appContentScrollTop(): number {
  return document.querySelector<HTMLElement>('[data-testid="app-content"]')?.scrollTop ?? 0;
}

export function rememberScroll(path: string, top: number): void {
  if (top <= 0) {
    pending.delete(path);
    return;
  }
  pending.delete(path);
  pending.set(path, top);
  if (pending.size > MAX_ENTRIES) {
    const oldest = pending.keys().next().value;
    if (oldest !== undefined) pending.delete(oldest);
  }
}

/** Consume the saved offset for this route, if the overlay just closed. */
export function takeScroll(path: string): number | null {
  const top = pending.get(path);
  if (top === undefined) return null;
  pending.delete(path);
  return top;
}

export function clearScrollMemory(): void {
  pending.clear();
}
