import { useEffect, useRef } from "react";

import {
  disposeOwner,
  subscribe,
  type BusEvent,
  type EventAck,
  type SubscribeOptions,
} from "../lib/eventBus";

let instanceSeq = 0;

function nextInstanceId(): string {
  instanceSeq += 1;
  return `component-${instanceSeq}`;
}

/**
 * A stable id for this component instance. The bus keeps one queue per
 * instance and event type; all of them are dropped when it unmounts.
 *
 * The id is a general "independent queue owner": it can identify a React
 * component, or a standalone logical subscription point when one component
 * deliberately needs several queues.
 */
export function useEventInstanceId(): string {
  const ref = useRef<string | null>(null);
  if (ref.current === null) ref.current = nextInstanceId();
  const id = ref.current;
  useEffect(() => () => disposeOwner(id), [id]);
  return id;
}

/**
 * Subscribe this instance to one event type with a stable handler ref.
 *
 * The first subscription on an instance/type queue must omit `override`;
 * replacing an existing handler requires `{ override: true }`.
 */
export function useBusSubscription<E extends BusEvent>(
  instanceId: string,
  type: E["type"],
  handler: (event: E) => EventAck | void,
  options: SubscribeOptions = {},
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const override = options.override === true;
  useEffect(
    () =>
      subscribe<E>(instanceId, type, (event) => handlerRef.current(event), {
        override,
      }),
    [instanceId, override, type],
  );
}
