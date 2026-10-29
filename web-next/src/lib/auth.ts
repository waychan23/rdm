// Stateless session state (§17). Tokens live in localStorage (see oauth.ts);
// this module caches the current whoami payload for the router guard and the
// top bar. A module singleton (not context) so router loaders can call
// ensureSession() outside the React tree; components subscribe with
// useCurrentUser().
import { useSyncExternalStore } from "react";

import { api } from "./api";
import { clearTokens, getAccessToken } from "./oauth";
import type { Whoami } from "../types";

let currentUser: Whoami | null = null;
let readiness: Promise<Whoami | null> | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

async function fetchWhoami(): Promise<Whoami | null> {
  if (!getAccessToken()) return null;
  try {
    return (await api.get<Whoami>("/whoami")).data;
  } catch {
    return null;
  }
}

/** Resolve the identity once per page load; reuse the in-flight promise. */
export function ensureSession(): Promise<Whoami | null> {
  if (currentUser) return Promise.resolve(currentUser);
  readiness ??= fetchWhoami().then((u) => {
    currentUser = u;
    emit();
    return u;
  });
  return readiness;
}

/** Replace the cached identity after a fresh login/callback. */
export async function reloadSession(): Promise<Whoami | null> {
  readiness = null;
  currentUser = null;
  return ensureSession();
}

/**
 * Re-fetch identity without clearing the current one first (no rail/topbar
 * flicker). Used by the AppShell poll and after self-affecting changes such as
 * transferring Org Owner.
 */
export async function refreshSession(): Promise<Whoami | null> {
  const user = await fetchWhoami();
  currentUser = user;
  emit();
  return user;
}

export interface LoginResult {
  must_reset: boolean;
  redirect_to?: string;
  set_password_url?: string;
}

/** Submit the SPA login form for an OAuth login ticket. */
export async function submitLogin(
  authKey: string,
  name: string,
  password: string,
  remember: boolean,
): Promise<LoginResult> {
  return (
    await api.post<LoginResult>("/auth/login", {
      auth_key: authKey,
      name,
      password,
      remember,
    })
  ).data;
}

export async function logout() {
  try {
    if (getAccessToken()) await api.post("/auth/logout", {});
  } finally {
    clearTokens();
    currentUser = null;
    readiness = null;
    emit();
  }
}

export function clearSession() {
  currentUser = null;
  readiness = null;
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useCurrentUser(): Whoami | null {
  return useSyncExternalStore(
    subscribe,
    () => currentUser,
    () => null,
  );
}
