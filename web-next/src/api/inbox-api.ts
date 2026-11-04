// Inbox notifications and the aggregated todo bundle.

import { api, type Envelope } from "../lib/api";
import type { Notification, TodoBundle } from "../types";
import { encode, withQuery, type Query } from "./query";

export function listNotifications(query?: Query): Promise<Envelope<Notification[]>> {
  return api.get<Notification[]>(withQuery("/notifications", query));
}

export function markNotificationsRead(ids: string[], identity?: string | null): Promise<void> {
  return api
    .post("/notifications/read", {
      ids,
      ...(identity ? { identity } : {}),
    })
    .then(() => undefined);
}

export function markAllNotificationsRead(identity?: string | null): Promise<number> {
  return api
    .post<{ updated: number }>("/notifications/read-all", {
      ...(identity ? { identity } : {}),
    })
    .then((res) => res.data.updated);
}

export function getTodos(identity?: string | null): Promise<TodoBundle> {
  const query = identity ? `identity=${encode(identity)}` : "";
  return api.get<TodoBundle>(withQuery("/todos", query)).then((res) => res.data);
}
