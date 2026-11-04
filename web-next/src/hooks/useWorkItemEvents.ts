import { useCallback, useEffect, useRef } from "react";

import { useBusSubscription } from "./useEventBus";
import {
  drain,
  KEEP,
  CONSUMED,
  type EventAck,
  type SubscribeOptions,
} from "../lib/eventBus";
import {
  WORK_ITEM_UPDATED,
  type WorkItemUpdatedEvent,
} from "../lib/workItemEvents";

/** Subscribe this instance to `work_item_updated` with a stable handler ref. */
export function useWorkItemUpdatedSubscription(
  instanceId: string,
  handler: (event: WorkItemUpdatedEvent) => EventAck | void,
  options: SubscribeOptions = {},
): void {
  useBusSubscription<WorkItemUpdatedEvent>(
    instanceId,
    WORK_ITEM_UPDATED,
    handler,
    options,
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
 * List-page glue for work item updates: consume relevant events immediately
 * while visible, keep them while a drawer covers the page, then batch-process
 * the queue once the last drawer closes (RDM-150).
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
      const queued = drain(
        instanceId,
        WORK_ITEM_UPDATED,
      ) as WorkItemUpdatedEvent[];
      if (queued.some((event) => !matchesRef.current || matchesRef.current(event))) {
        scheduleRefresh();
      }
    }
    wasVisible.current = visible;
  }, [instanceId, visible, scheduleRefresh]);
}
