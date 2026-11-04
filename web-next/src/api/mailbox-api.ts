// Internal mailbox: message listing, read/archive/delete actions, mail groups
// (project mailboxes) and composing project messages.

import { api } from "../lib/api";
import type { Mailbox, MailGroup } from "../types";
import { encode, withQuery, type Query } from "./query";

export function getMailbox(
  projectKey: string | null,
  query?: Query,
): Promise<Mailbox> {
  const path = projectKey ? `/projects/${encode(projectKey)}/mailbox` : "/mailbox";
  return api.get<Mailbox>(withQuery(path, query)).then((res) => res.data);
}

export function markMessagesRead(deliveryIds: string[]): Promise<void> {
  return api
    .post("/messages/read", { delivery_ids: deliveryIds })
    .then(() => undefined);
}

export function archiveMessages(deliveryIds: string[], archived: boolean): Promise<void> {
  return api
    .post("/messages/archive", { delivery_ids: deliveryIds, archived })
    .then(() => undefined);
}

export function deleteMessages(deliveryIds: string[]): Promise<void> {
  return api
    .post("/messages/delete", { delivery_ids: deliveryIds })
    .then(() => undefined);
}

export function listMailGroups(projectKey: string): Promise<MailGroup[]> {
  return api
    .get<MailGroup[]>(`/projects/${encode(projectKey)}/mailboxes`)
    .then((res) => res.data);
}

export function createMailGroup(
  projectKey: string,
  payload: { name: string; members: string[] },
): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/mailboxes`, payload)
    .then(() => undefined);
}

export interface SendMessageInput {
  to: string[];
  subject: string;
  body_md: string;
  cc: string[];
  refs: string[];
  reply_to: string | null;
}

export function sendProjectMessage(
  projectKey: string,
  payload: SendMessageInput,
): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/messages`, payload)
    .then(() => undefined);
}
