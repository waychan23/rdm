/**
 * In-browser publish/subscribe bus for cross-component refresh (RDM-150).
 *
 * Each subscriber owns one queue per event type. Publishing pushes the event
 * into every subscribed queue and runs the handlers immediately; a handler can
 * ACK the event (return `CONSUMED`) to drop it from the queue, or keep it
 * (`KEEP`) so a component that is currently covered can batch-process it when
 * it becomes visible again.
 *
 * Queues are keyed by component-instance id, so unmounting an instance
 * (`disposeOwner`) drops its unread events and prevents leaks.
 */

export const CONSUMED = "CONSUMED" as const;
export const KEEP = "KEEP" as const;
export type EventAck = typeof CONSUMED | typeof KEEP;

export interface WorkItemUpdatedEvent {
  type: "work_item_updated";
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

export type BusEvent = WorkItemUpdatedEvent;
export type BusEventType = BusEvent["type"];

export type EventHandler<E extends BusEvent = BusEvent> = (
  event: E,
) => EventAck | void;

interface OwnerQueue {
  ownerId: string;
  type: BusEventType;
  events: BusEvent[];
  handlers: EventHandler[];
}

const queues = new Map<string, OwnerQueue>();
const owners = new Map<string, Set<string>>();

function queueKey(ownerId: string, type: BusEventType): string {
  return `${ownerId}\u0000${type}`;
}

function ownerKeys(ownerId: string): Set<string> {
  let set = owners.get(ownerId);
  if (!set) {
    set = new Set();
    owners.set(ownerId, set);
  }
  return set;
}

/** Subscribe an instance to one event type. Returns an unsubscribe function. */
export function subscribe<E extends BusEvent = BusEvent>(
  ownerId: string,
  type: E["type"],
  handler: EventHandler<E>,
): () => void {
  const key = queueKey(ownerId, type);
  let queue = queues.get(key);
  if (!queue) {
    queue = { ownerId, type, events: [], handlers: [] };
    queues.set(key, queue);
    ownerKeys(ownerId).add(key);
  }
  queue.handlers.push(handler as EventHandler);
  return () => {
    const current = queues.get(key);
    if (!current) return;
    current.handlers = current.handlers.filter((item) => item !== handler);
    if (current.handlers.length === 0) {
      // Unsubscribing also discards the instance's unread events for this type.
      queues.delete(key);
      ownerKeys(ownerId).delete(key);
    }
  };
}

/** Drop every queue an instance owns (component unmount). */
export function disposeOwner(ownerId: string): void {
  const keys = owners.get(ownerId);
  if (!keys) return;
  for (const key of keys) queues.delete(key);
  owners.delete(ownerId);
}

/**
 * Publish an event: enqueue it for every subscriber, then let their handlers
 * decide synchronously whether to consume it.
 */
export function publish(event: BusEvent): void {
  for (const queue of [...queues.values()]) {
    if (queue.type !== event.type) continue;
    queue.events.push(event);
    for (const handler of [...queue.handlers]) {
      let ack: EventAck | void;
      try {
        ack = handler(event);
      } catch {
        // A broken handler must not lose the event; keep it for the next drain.
        ack = KEEP;
      }
      if (ack === CONSUMED) {
        const index = queue.events.indexOf(event);
        if (index >= 0) queue.events.splice(index, 1);
        break;
      }
    }
  }
}

/** Read (without consuming) the queued events for an instance. */
export function pending(
  ownerId: string,
  type: BusEventType,
): readonly BusEvent[] {
  return queues.get(queueKey(ownerId, type))?.events ?? [];
}

/**
 * Take every queued event for an instance: the caller batch-processes them and
 * owns the ACK (they are removed from the queue).
 */
export function drain(ownerId: string, type: BusEventType): BusEvent[] {
  const queue = queues.get(queueKey(ownerId, type));
  if (!queue || queue.events.length === 0) return [];
  const events = queue.events;
  queue.events = [];
  return events;
}

/** Publish the common "this work item changed" event. */
export function publishWorkItemUpdated(
  event: Omit<WorkItemUpdatedEvent, "type" | "eventTime"> & { eventTime?: number },
): void {
  publish({
    type: "work_item_updated",
    eventTime: event.eventTime ?? Date.now(),
    ...event,
  });
}
