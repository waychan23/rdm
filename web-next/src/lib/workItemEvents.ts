/**
 * Work-item domain events carried by the neutral event bus.
 *
 * Keeping the payload shape and publish helpers here means `eventBus.ts` and
 * `hooks/useEventBus.ts` stay business-agnostic.
 */

import { publish, type BusEvent } from "./eventBus";

export const WORK_ITEM_UPDATED = "work_item_updated" as const;

export interface WorkItemUpdatedEvent extends BusEvent {
  type: typeof WORK_ITEM_UPDATED;
  /** Event time, used to order/batch queued events. */
  eventTime: number;
  projectKey: string;
  workItemId: string;
  displayId?: string;
  /** Parent after the change (null when the item is now a root). */
  parentId?: string | null;
  /** Parent before the change, so a reparent also wakes the old parent. */
  previousParentId?: string | null;
  action: "created" | "updated" | "deleted";
  /** Component instance that caused the change; it already refreshed itself. */
  source?: string;
}

/** Publish the common "this work item changed" event. */
export function publishWorkItemUpdated(
  event: Omit<WorkItemUpdatedEvent, "type" | "eventTime"> & {
    eventTime?: number;
  },
): void {
  publish({
    type: WORK_ITEM_UPDATED,
    eventTime: event.eventTime ?? Date.now(),
    ...event,
  });
}
