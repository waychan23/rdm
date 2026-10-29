// Item detail is a route-backed overlay; remember where it was opened from so
// closing returns to the list (or to the parent item when drilled in).

export interface ItemLocationState {
  from?: string;
}

export function itemPath(projectKey: string, itemId: string): string {
  return `/projects/${projectKey}/items/${itemId}`;
}

export function withOrigin(from: string): ItemLocationState {
  return { from };
}

export function originFor(state: unknown, fallback: string): string {
  if (state && typeof state === "object" && "from" in state) {
    const from = (state as ItemLocationState).from;
    if (typeof from === "string" && from.startsWith("/projects/")) return from;
  }
  return fallback;
}
