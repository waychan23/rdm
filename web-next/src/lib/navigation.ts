// Item detail is a route-backed overlay; remember where it was opened from so
// closing returns to the list (or to the parent item when drilled in).

export interface ItemLocationState {
  from?: string;
}

export function itemPath(projectKey: string, itemId: string): string {
  return `/projects/${projectKey}/items/${itemId}`;
}

export function originFor(state: unknown, fallback: string): string {
  if (state && typeof state === "object" && "from" in state) {
    const from = (state as ItemLocationState).from;
    // Any in-app page can own the drawer backdrop (inbox, mailbox, search…);
    // only relative-to-protocol ("//host") and external URLs are rejected.
    if (typeof from === "string" && from.startsWith("/") && !from.startsWith("//")) {
      return from;
    }
  }
  return fallback;
}
