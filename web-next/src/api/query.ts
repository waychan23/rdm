// Shared helpers for the api service layer. Callers may pass either an
// already-built URLSearchParams or a raw query string; service modules own the
// path and only ever see the search part.

export type Query = URLSearchParams | string;

export function encode(value: string): string {
  return encodeURIComponent(value);
}

/** Append a search string to a REST path, omitting the `?` when empty. */
export function withQuery(path: string, query?: Query | null): string {
  const search = typeof query === "string" ? query : (query?.toString() ?? "");
  return search ? `${path}?${search}` : path;
}
