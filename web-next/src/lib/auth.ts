// Stateless session state (§17). Tokens live in localStorage (see oauth.ts);
// this module caches the current whoami payload for the router guard and the
// top bar. A module singleton (not context) so router loaders can call
// ensureSession() outside the React tree; components subscribe with
// useCurrentUser().
import { useSyncExternalStore } from "react";

import {
  fetchWhoami as fetchWhoamiApi,
  submitLogin as submitLoginApi,
  submitLogout,
} from "../api/auth-api";
import { clearTokens, getAccessToken } from "./oauth";
import { clearPageCache } from "./pageCache";
import { clearProjectMembersCache } from "./members";
import { clearScrollMemory } from "./scrollMemory";
import { clearViewMemory } from "../workitems/viewMemory";
import type { Whoami } from "../types";

let currentUser: Whoami | null = null;
let readiness: Promise<Whoami | null> | null = null;
// When the identity was last fetched successfully. Lets the shell avoid
// re-fetching what the router loader just resolved (Bug: duplicate /whoami).
let lastFetchedAt = 0;
// Single-flight for forced refreshes (poll / SSE / post-mutation can overlap).
let refreshInFlight: Promise<Whoami | null> | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

async function loadWhoami(): Promise<Whoami | null> {
  if (!getAccessToken()) return null;
  try {
    const user = await fetchWhoamiApi();
    lastFetchedAt = Date.now();
    return user;
  } catch {
    return null;
  }
}

/** Resolve the identity once per page load; reuse the in-flight promise. */
export function ensureSession(): Promise<Whoami | null> {
  if (currentUser) return Promise.resolve(currentUser);
  readiness ??= loadWhoami().then((u) => {
    currentUser = u;
    emit();
    return u;
  });
  return readiness;
}

/** Replace the cached identity after a fresh login/callback. */
export async function reloadSession(): Promise<Whoami | null> {
  readiness = null;
  refreshInFlight = null;
  lastFetchedAt = 0;
  currentUser = null;
  clearProjectMembersCache();
  return ensureSession();
}

/**
 * Re-fetch identity without clearing the current one first (no rail/topbar
 * flicker). Used by the AppShell poll and after self-affecting changes such as
 * transferring Org Owner. Concurrent callers share one request.
 */
export function refreshSession(): Promise<Whoami | null> {
  if (refreshInFlight) return refreshInFlight;
  const request = loadWhoami().then((user) => {
    currentUser = user;
    emit();
    return user;
  });
  const pending = request.finally(() => {
    if (refreshInFlight === pending) refreshInFlight = null;
  });
  refreshInFlight = pending;
  return pending;
}

/**
 * Refresh only when the cached identity is older than `maxAgeMs`. The router
 * loader has just fetched it on hard load, so the shell mount should not issue
 * a second `/whoami`. A null identity is always retried.
 */
export function refreshSessionIfStale(
  maxAgeMs = 30_000,
): Promise<Whoami | null> {
  if (currentUser && Date.now() - lastFetchedAt <= maxAgeMs) {
    return Promise.resolve(currentUser);
  }
  return refreshSession();
}

/** Submit the SPA login form for an OAuth login ticket. */
export function submitLogin(
  authKey: string,
  name: string,
  password: string,
  remember: boolean,
) {
  return submitLoginApi({ authKey, name, password, remember });
}

export async function logout() {
  try {
    if (getAccessToken()) await submitLogout();
  } finally {
    clearPageCache();
    clearScrollMemory();
    clearViewMemory();
    clearProjectMembersCache();
    clearTokens();
    currentUser = null;
    readiness = null;
    refreshInFlight = null;
    lastFetchedAt = 0;
    emit();
  }
}

export function clearSession() {
  clearPageCache();
  clearScrollMemory();
  clearViewMemory();
  clearProjectMembersCache();
  currentUser = null;
  readiness = null;
  refreshInFlight = null;
  lastFetchedAt = 0;
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
