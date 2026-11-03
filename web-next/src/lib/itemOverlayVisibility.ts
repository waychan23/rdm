import { useEffect, useSyncExternalStore } from "react";

/**
 * Tracks how many work item drawer hosts/layers are open (RDM-150). A list
 * page uses this to keep update events queued while its drawer covers it, and
 * to batch-refresh when the last layer closes.
 *
 * Counts are keyed by host so the route-backed drawer and the in-page overlay
 * cannot overwrite each other when both are mounted by the router.
 */
const layerCounts = new Map<string, number>();
const listeners = new Set<() => void>();
let hostSeq = 0;

/** Unique id for a drawer host (in-page stack vs. route-backed panel). */
export function nextItemOverlayHostId(): string {
  hostSeq += 1;
  return `overlay-host-${hostSeq}`;
}

function totalLayers(): number {
  let total = 0;
  for (const count of layerCounts.values()) total += count;
  return total;
}

function emit(): void {
  for (const listener of listeners) listener();
}

export function setItemOverlayLayers(hostId: string, count: number): void {
  const current = layerCounts.get(hostId) ?? 0;
  if (current === count) return;
  if (count > 0) layerCounts.set(hostId, count);
  else layerCounts.delete(hostId);
  emit();
}

export function itemOverlayLayerCount(): number {
  return totalLayers();
}

export function itemOverlayOpen(): boolean {
  return totalLayers() > 0;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** True while at least one work item drawer layer is open anywhere. */
export function useItemOverlayOpen(): boolean {
  return useSyncExternalStore(subscribe, itemOverlayOpen, itemOverlayOpen);
}

/** Register one host's layer count; it is cleared when the host unmounts. */
export function useItemOverlayHost(hostId: string, count: number): void {
  useEffect(() => {
    setItemOverlayLayers(hostId, count);
    return () => setItemOverlayLayers(hostId, 0);
  }, [hostId, count]);
}
