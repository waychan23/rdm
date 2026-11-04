/**
 * Business-neutral in-browser publish/subscribe bus.
 *
 * Each subscriber owns one queue per event type. Publishing pushes the event
 * into every subscribed queue and runs the queue's handler immediately; the
 * handler can ACK the event (return `CONSUMED`) to drop it, or keep it
 * (`KEEP`) so a component that is currently covered can batch-process it when
 * it becomes visible again.
 *
 * A queue has exactly one handler: when a subscriber replaces it, it must pass
 * `override: true` explicitly, and a first-time subscription must not pass it.
 * This makes accidental double-subscription a loud error instead of silently
 * dropping events for one of the handlers. A component that genuinely needs
 * several independent queues should use a different owner/instance id per
 * subscription point.
 *
 * Queues are keyed by owner id + event type; unmounting an owner
 * (`disposeOwner`) drops its unread events and prevents leaks.
 */

export const CONSUMED = "CONSUMED" as const;
export const KEEP = "KEEP" as const;
export type EventAck = typeof CONSUMED | typeof KEEP;

/** Minimal shape every bus event must satisfy. */
export interface BusEvent {
  type: string;
}

export type EventHandler<E extends BusEvent = BusEvent> = (
  event: E,
) => EventAck | void;

export interface SubscribeOptions {
  /**
   * Explicitly replace the handler already registered for this owner + type.
   * Omit on the first subscription; passing it then is an error too.
   */
  override?: boolean;
}

export class SubscriptionConflictError extends Error {
  constructor(ownerId: string, type: string) {
    super(
      `subscription for ${ownerId}/${type} already exists; ` +
        "pass { override: true } to replace it deliberately, or use a " +
        "different instance id for an independent queue",
    );
    this.name = "SubscriptionConflictError";
  }
}

export class SubscriptionOverrideError extends Error {
  constructor(ownerId: string, type: string) {
    super(
      `{ override: true } was passed for ${ownerId}/${type} but no ` +
        "subscription exists; omit override on the first subscription",
    );
    this.name = "SubscriptionOverrideError";
  }
}

interface OwnerQueue {
  ownerId: string;
  type: string;
  events: BusEvent[];
  handler: EventHandler;
}

const queues = new Map<string, OwnerQueue>();
const owners = new Map<string, Set<string>>();

function queueKey(ownerId: string, type: string): string {
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

/**
 * Subscribe an instance to one event type. Returns an unsubscribe function.
 *
 * The first subscription on a queue must omit `override`; replacing an
 * existing handler requires `{ override: true }`.
 */
export function subscribe<E extends BusEvent>(
  ownerId: string,
  type: E["type"],
  handler: EventHandler<E>,
  options: SubscribeOptions = {},
): () => void {
  const key = queueKey(ownerId, type);
  const existing = queues.get(key);
  const override = options.override === true;

  if (existing) {
    if (!override) throw new SubscriptionConflictError(ownerId, type);
    // Keep the queued (unread) events: the new handler takes over the queue.
    existing.handler = handler as EventHandler;
  } else {
    if (override) {
      // `override` means "replace something"; there is nothing to replace.
      throw new SubscriptionOverrideError(ownerId, type);
    }
    queues.set(key, {
      ownerId,
      type,
      events: [],
      handler: handler as EventHandler,
    });
    ownerKeys(ownerId).add(key);
  }

  return () => {
    const current = queues.get(key);
    // A replaced handler's stale unsubscribe must not remove the new one.
    if (!current || current.handler !== handler) return;
    queues.delete(key);
    ownerKeys(ownerId).delete(key);
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
 * Publish an event: enqueue it for every subscriber, then let each handler
 * decide synchronously whether to consume it.
 */
export function publish(event: BusEvent): void {
  for (const queue of [...queues.values()]) {
    if (queue.type !== event.type) continue;
    queue.events.push(event);
    let ack: EventAck | void;
    try {
      ack = queue.handler(event);
    } catch {
      // A broken handler must not lose the event; keep it for the next drain.
      ack = KEEP;
    }
    if (ack === CONSUMED) {
      const index = queue.events.indexOf(event);
      if (index >= 0) queue.events.splice(index, 1);
    }
  }
}

/** Read (without consuming) the queued events for an instance. */
export function pending(
  ownerId: string,
  type: string,
): readonly BusEvent[] {
  return queues.get(queueKey(ownerId, type))?.events ?? [];
}

/**
 * Take every queued event for an instance: the caller batch-processes them and
 * owns the ACK (they are removed from the queue).
 */
export function drain(ownerId: string, type: string): BusEvent[] {
  const queue = queues.get(queueKey(ownerId, type));
  if (!queue || queue.events.length === 0) return [];
  const events = queue.events;
  queue.events = [];
  return events;
}
