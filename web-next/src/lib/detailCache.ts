// Last-loaded detail payloads for sprint/release drawers. The item drawer route
// unmounts the page behind it; without a cache the drawer would re-mount empty
// for a frame (and flash) before its fetch resolves. Entries are refreshed by
// every load, so a stale value is only ever shown while the fetch is in flight.
const cache = new Map<string, unknown>();

export function rememberDetail<T>(key: string, value: T): void {
  cache.set(key, value);
}

export function recallDetail<T>(key: string): T | null {
  return (cache.get(key) as T | undefined) ?? null;
}
