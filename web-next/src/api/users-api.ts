// Organization users (admin), personal settings, tokens and owned agents.

import { api } from "../lib/api";
import type { OrgUser, Token } from "../types";
import { encode } from "./query";

export type NotificationPrefs = Record<string, Record<string, boolean>>;

export interface CreateUserInput {
  name: string;
  display_name: string | null;
  email: string | null;
}

export interface CreateUserResult {
  user: OrgUser;
  password_reset_url: string;
}

export interface AgentInput {
  name: string;
  display_name: string | null;
  accept_kinds: string[];
  email: string | null;
  notify_webhook: string | null;
  notify_webhook_format: string;
}

export interface AgentPatch {
  display_name?: string | null;
  notify_webhook?: string | null;
  notify_webhook_format?: string;
  is_active?: boolean;
}

export interface ProfileInput {
  display_name: string | null;
  email: string | null;
  notify_webhook: string | null;
  notify_webhook_format: string;
}

export function listUsers(type?: "human"): Promise<OrgUser[]> {
  const query = type ? `?type=${encode(type)}` : "";
  return api.get<OrgUser[]>(`/users${query}`).then((res) => res.data);
}

export function createUser(input: CreateUserInput): Promise<CreateUserResult> {
  return api
    .post<CreateUserResult>("/users", {
      name: input.name.trim(),
      display_name: input.display_name?.trim() || null,
      email: input.email || null,
    })
    .then((res) => res.data);
}

export function createPasswordResetToken(
  userId: string,
): Promise<{ password_reset_url: string }> {
  return api
    .post<{ password_reset_url: string }>(
      `/users/${encode(userId)}/password-reset-token`,
    )
    .then((res) => res.data);
}

export function setUserActive(userId: string, active: boolean): Promise<void> {
  const action = active ? "enable" : "disable";
  return api.post(`/users/${encode(userId)}/${action}`).then(() => undefined);
}

export function revokeAllUserTokens(userId: string): Promise<void> {
  return api
    .post(`/users/${encode(userId)}/tokens/revoke-all`)
    .then(() => undefined);
}

export function updateUser(
  userId: string,
  payload: {
    display_name: string | null;
    email: string | null;
    description_md: string | null;
  },
): Promise<void> {
  return api.patch(`/users/${encode(userId)}`, payload).then(() => undefined);
}

export function setUserOrgRoles(userId: string, roles: string[]): Promise<void> {
  return api
    .put(`/users/${encode(userId)}/org-roles`, { roles })
    .then(() => undefined);
}

export function transferOrgOwner(userId: string): Promise<void> {
  return api.post("/org/transfer-owner", { user_id: userId }).then(() => undefined);
}

export function listMyTokens(): Promise<Token[]> {
  return api.get<Token[]>("/me/tokens").then((res) => res.data);
}

export function createMyToken(body: Record<string, unknown>): Promise<Token> {
  return api.post<Token>("/me/tokens", body).then((res) => res.data);
}

export function revokeMyToken(tokenId: string): Promise<void> {
  return api.del(`/me/tokens/${encode(tokenId)}`).then(() => undefined);
}

export function listMyAgents(): Promise<OrgUser[]> {
  return api.get<OrgUser[]>("/me/agents").then((res) => res.data);
}

export function createMyAgent(input: AgentInput): Promise<void> {
  return api
    .post("/me/agents", {
      name: input.name.trim(),
      display_name: input.display_name?.trim() || null,
      accept_kinds: input.accept_kinds,
      email: input.email || null,
      notify_webhook: input.notify_webhook || null,
      notify_webhook_format: input.notify_webhook_format,
    })
    .then(() => undefined);
}

export function updateMyAgent(agentId: string, patch: AgentPatch): Promise<void> {
  return api.patch(`/me/agents/${encode(agentId)}`, patch).then(() => undefined);
}

export function updateMe(patch: ProfileInput): Promise<void> {
  return api.patch("/me", patch).then(() => undefined);
}

export function getNotificationPrefs(): Promise<NotificationPrefs> {
  return api
    .get<{ prefs: NotificationPrefs }>("/me/notification-prefs")
    .then((res) => res.data.prefs);
}

export function updateNotificationPrefs(
  patch: Record<string, Record<string, boolean>>,
): Promise<void> {
  return api.patch("/me/notification-prefs", { prefs: patch }).then(() => undefined);
}
