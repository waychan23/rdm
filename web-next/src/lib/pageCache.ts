// Short-lived snapshots for list pages that get remounted when the
// route-backed work-item overlay opens or closes. Without them the list drops
// to its loading spinner while re-fetching data it just showed, which reads as
// a flash. Reads are synchronous and the page still revalidates in the
// background; this is presentation continuity, not a source of truth.
const MAX_ENTRIES = 24;
const snapshots = new Map<string, unknown>();

export function recall<T>(key: string): T | undefined {
  return snapshots.get(key) as T | undefined;
}

export function remember<T>(key: string, value: T): void {
  // Refresh insertion order so the least recently written entry is evicted.
  snapshots.delete(key);
  snapshots.set(key, value);
  if (snapshots.size > MAX_ENTRIES) {
    const oldest = snapshots.keys().next().value;
    if (oldest !== undefined) snapshots.delete(oldest);
  }
}

/** Drop cached pages when the session/identity changes. */
export function clearPageCache(): void {
  snapshots.clear();
}
