import { api } from "./api";
import { apiLocale } from "../i18n";
import { getAccessToken } from "./oauth";
import type { OrgUser, ProjectMemberRow } from "../types";

/** Flatten the folded members response (humans + their agents) to one list. */
export function flattenMembers(rows: ProjectMemberRow[]): OrgUser[] {
  const out: OrgUser[] = [];
  for (const row of rows) {
    out.push(row);
    for (const agent of row.agents ?? []) out.push(agent.user);
  }
  return out;
}

// A project's member list is read by many independent components (mention
// pickers, people fields, item panels, mailbox, settings). Without a shared
// loader they each issue their own GET, and dialog transitions can briefly
// keep several consumers mounted at once. This is a short-lived consistency
// cache, not a source of truth: local member mutations invalidate it, and the
// TTL bounds staleness for out-of-band changes.
const TTL_MS = 30_000;

interface CacheEntry {
  rows: ProjectMemberRow[];
  at: number;
}

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<ProjectMemberRow[]>>();
let identityEpoch = `${getAccessToken() ?? ""}\u0000${apiLocale()}`;
// Bumped by every invalidation so an in-flight pre-mutation response cannot
// write its stale payload back into the cache.
let generation = 0;

function currentIdentityEpoch(): string {
  return `${getAccessToken() ?? ""}\u0000${apiLocale()}`;
}

function ensureIdentityEpoch(): void {
  const next = currentIdentityEpoch();
  if (next === identityEpoch) return;
  identityEpoch = next;
  generation += 1;
  cache.clear();
  inflight.clear();
}

/**
 * Load one project's member rows through a shared single-flight + TTL cache.
 * Empty project keys resolve to an empty list without a request.
 */
export function loadProjectMembers(
  projectKey: string,
  options: { force?: boolean } = {},
): Promise<ProjectMemberRow[]> {
  if (!projectKey) return Promise.resolve([]);
  ensureIdentityEpoch();
  if (options.force) invalidateProjectMembers(projectKey);

  const cached = cache.get(projectKey);
  if (cached && Date.now() - cached.at < TTL_MS) {
    return Promise.resolve(cached.rows);
  }
  const pending = inflight.get(projectKey);
  if (pending) return pending;

  const requestGeneration = generation;
  const request = api
    .get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)
    .then((res) => {
      // Only cache if no identity switch / invalidation happened meanwhile.
      if (generation === requestGeneration) {
        cache.set(projectKey, { rows: res.data, at: Date.now() });
      }
      return res.data;
    })
    .finally(() => {
      if (inflight.get(projectKey) === request) inflight.delete(projectKey);
    });
  inflight.set(projectKey, request);
  return request;
}

/** Drop one project's cached list, or every project's when no key is given. */
export function invalidateProjectMembers(projectKey?: string): void {
  generation += 1;
  if (projectKey) {
    cache.delete(projectKey);
    inflight.delete(projectKey);
    return;
  }
  cache.clear();
  inflight.clear();
}

/** Session/logout cleanup: also forget the token/locale epoch. */
export function clearProjectMembersCache(): void {
  invalidateProjectMembers();
  identityEpoch = currentIdentityEpoch();
}
