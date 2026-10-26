// Console session state (M3.1). The browser authenticates with the
// HttpOnly rdm_session cookie issued by POST /api/v1/auth/login; this module
// only tracks the current member for the router guard and the top bar.
import { ref } from "vue";
import { api } from "./api";

export interface AuthMember {
  id: string;
  project_id: string;
  type: string;
  name: string;
  roles: string[];
  is_active: boolean;
}

const currentMember = ref<AuthMember | null>(null);
let readiness: Promise<AuthMember | null> | null = null;

async function fetchMe(): Promise<AuthMember | null> {
  try {
    return (await api.get<AuthMember>("/auth/me")).data;
  } catch {
    return null;
  }
}

/** Resolve the session once per page load; reuse the in-flight promise. */
export function ensureSession(): Promise<AuthMember | null> {
  if (currentMember.value) return Promise.resolve(currentMember.value);
  readiness ??= fetchMe().then((m) => {
    currentMember.value = m;
    return m;
  });
  return readiness;
}

export function sessionMember() {
  return currentMember;
}

export async function login(projectKey: string, name: string, password: string) {
  const member = (
    await api.post<AuthMember>("/auth/login", {
      project_key: projectKey,
      name,
      password,
    })
  ).data;
  currentMember.value = member;
  readiness = Promise.resolve(member);
  return member;
}

export async function logout() {
  try {
    await api.post("/auth/logout", {});
  } finally {
    currentMember.value = null;
    readiness = null;
  }
}

/** Drop cached identity after the API reports a 401 (expired session). */
export function clearSession() {
  currentMember.value = null;
  readiness = null;
}

const PROJECT_KEY_STORAGE = "rdm.projectKey";

export function rememberedProjectKey(): string {
  return localStorage.getItem(PROJECT_KEY_STORAGE) || "RDM";
}

export function rememberProjectKey(key: string) {
  localStorage.setItem(PROJECT_KEY_STORAGE, key);
}
