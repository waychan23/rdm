import { useCallback, useEffect, useRef } from "react";

import {
  CONSUMED,
  KEEP,
  drain,
  disposeOwner,
  subscribe,
  type EventAck,
  type WorkItemUpdatedEvent,
} from "../lib/eventBus";

let instanceSeq = 0;

function nextInstanceId(): string {
  instanceSeq += 1;
  return `component-${instanceSeq}`;
}

/**
 * A stable id for this component instance (RDM-150). The bus keeps one queue
 * per instance and event type; all of them are dropped when it unmounts.
 */
export function useEventInstanceId(): string {
  const ref = useRef<string | null>(null);
  if (ref.current === null) ref.current = nextInstanceId();
  const id = ref.current;
  useEffect(() => () => disposeOwner(id), [id]);
  return id;
}

/** Subscribe this instance to `work_item_updated`, with a stable handler ref. */
export function useWorkItemUpdatedSubscription(
  instanceId: string,
  handler: (event: WorkItemUpdatedEvent) => EventAck | void,
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  useEffect(
    () =>
      subscribe<WorkItemUpdatedEvent>(instanceId, "work_item_updated", (event) =>
        handlerRef.current(event),
      ),
    [instanceId],
  );
}

interface RefreshOptions {
  instanceId: string;
  /** The list is only actionable while no work item drawer covers it. */
  visible: boolean;
  /** Whether an event warrants a refresh (defaults to all events). */
  matches?: (event: WorkItemUpdatedEvent) => boolean;
  onRefresh: () => void;
}

/**
 * List-page glue for the event bus: consume relevant events immediately while
 * visible, keep them while a drawer covers the page, then batch-process the
 * queue once the last drawer closes (RDM-150).
 */
export function useWorkItemUpdatedRefresh({
  instanceId,
  visible,
  matches,
  onRefresh,
}: RefreshOptions): void {
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const matchesRef = useRef(matches);
  matchesRef.current = matches;
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;
  const timerRef = useRef<number | null>(null);

  // Coalesce several events published in the same tick into one reload.
  const scheduleRefresh = useCallback(() => {
    if (timerRef.current !== null) return;
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      refreshRef.current();
    }, 0);
  }, []);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  useWorkItemUpdatedSubscription(instanceId, (event) => {
    if (!visibleRef.current) return KEEP;
    if (!matchesRef.current || matchesRef.current(event)) scheduleRefresh();
    return CONSUMED;
  });

  const wasVisible = useRef(visible);
  useEffect(() => {
    if (!wasVisible.current && visible) {
      const queued = drain(instanceId, "work_item_updated") as WorkItemUpdatedEvent[];
      if (queued.some((event) => !matchesRef.current || matchesRef.current(event))) {
        scheduleRefresh();
      }
    }
    wasVisible.current = visible;
  }, [instanceId, visible, scheduleRefresh]);
}
