// Console session state. The browser authenticates with the HttpOnly
// rdm_session cookie issued by POST /api/v1/auth/login; this module only
// tracks the current member for the router guard and the top bar.
//
// A module singleton (not context) so router loaders can call ensureSession()
// outside the React tree; components subscribe with useCurrentMember().
import { useSyncExternalStore } from "react";

import { api } from "./api";

export interface AuthMember {
  id: string;
  project_id: string;
  type: string;
  name: string;
  roles: string[];
  is_active: boolean;
}

let currentMember: AuthMember | null = null;
let readiness: Promise<AuthMember | null> | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

async function fetchMe(): Promise<AuthMember | null> {
  try {
    return (await api.get<AuthMember>("/auth/me")).data;
  } catch {
    return null;
  }
}

/** Resolve the session once per page load; reuse the in-flight promise. */
export function ensureSession(): Promise<AuthMember | null> {
  if (currentMember) return Promise.resolve(currentMember);
  readiness ??= fetchMe().then((m) => {
    currentMember = m;
    emit();
    return m;
  });
  return readiness;
}

export async function login(projectKey: string, name: string, password: string) {
  const member = (
    await api.post<AuthMember>("/auth/login", {
      project_key: projectKey,
      name,
      password,
    })
  ).data;
  currentMember = member;
  readiness = Promise.resolve(member);
  emit();
  return member;
}

export async function logout() {
  try {
    await api.post("/auth/logout", {});
  } finally {
    clearSession();
  }
}

/** Drop cached identity after the API reports a 401 (expired session). */
export function clearSession() {
  currentMember = null;
  readiness = null;
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useCurrentMember(): AuthMember | null {
  return useSyncExternalStore(
    subscribe,
    () => currentMember,
    () => null,
  );
}

const PROJECT_KEY_STORAGE = "rdm.projectKey";

export function rememberedProjectKey(): string {
  return localStorage.getItem(PROJECT_KEY_STORAGE) || "RDM";
}

export function rememberProjectKey(key: string) {
  localStorage.setItem(PROJECT_KEY_STORAGE, key);
}
