// Authentication and consent endpoints. Everything the SPA does against
// /auth, /whoami and /oauth/consent lives here; callers never build these paths.

import { apiLocale } from "../i18n";
import { api, apiUrl } from "../lib/api";
import type { OrgUser, Whoami } from "../types";
import { encode } from "./query";

export interface LoginResult {
  must_reset: boolean;
  redirect_to?: string;
  set_password_url?: string;
}

export interface PasswordTicketStatus {
  valid: boolean;
  reason: string | null;
  kind: string | null;
  expires_at: string | null;
}

export interface ConsentInfo {
  client: { client_id: string; client_name: string | null };
  scopes: string[];
  selectable_users: OrgUser[];
}

export type ConsentDecision =
  | { decision: "allow"; act_as_user_id: string }
  | { decision: "deny" };

export function fetchWhoami(): Promise<Whoami> {
  return api.get<Whoami>("/whoami").then((res) => res.data);
}

export function submitLogin(credentials: {
  authKey: string;
  name: string;
  password: string;
  remember: boolean;
}): Promise<LoginResult> {
  return api
    .post<LoginResult>("/auth/login", {
      auth_key: credentials.authKey,
      name: credentials.name,
      password: credentials.password,
      remember: credentials.remember,
    })
    .then((res) => res.data);
}

export function submitLogout(): Promise<void> {
  return api.post("/auth/logout", {}).then(() => undefined);
}

export function checkPasswordTicket(ticket: string): Promise<PasswordTicketStatus> {
  return api
    .post<PasswordTicketStatus>("/auth/password-ticket/check", { ticket })
    .then((res) => res.data);
}

export function setPasswordWithTicket(ticket: string, newPassword: string): Promise<void> {
  return api
    .post("/auth/set-password", { ticket, new_password: newPassword })
    .then(() => undefined);
}

export function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  return api
    .post("/auth/password", { old_password: oldPassword, new_password: newPassword })
    .then(() => undefined);
}

// The consent flow is authorized by a one-shot capability key in the URL, not
// by the Bearer token, so it must bypass the authenticated client (§17).
async function consentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: { "Accept-Language": apiLocale(), ...(init?.headers ?? {}) },
  });
  const payload = (await res.json()) as { data?: T; error?: { message?: string } };
  if (!res.ok) throw new Error(payload?.error?.message ?? `HTTP ${res.status}`);
  return payload.data as T;
}

export function fetchConsentInfo(id: string, key: string): Promise<ConsentInfo> {
  return consentRequest<ConsentInfo>(
    `/oauth/consent/${encode(id)}?key=${encode(key)}`,
  );
}

export function submitConsentDecision(
  id: string,
  key: string,
  decision: ConsentDecision,
): Promise<{ redirect_to: string }> {
  return consentRequest<{ redirect_to: string }>(
    `/oauth/consent/${encode(id)}/decision?key=${encode(key)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    },
  );
}
