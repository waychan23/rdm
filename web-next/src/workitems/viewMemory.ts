import { useEffect } from "react";

import { useListSearchParams } from "../lib/originSearch";

/**
 * Per-project view memory for the three work item pages (RDM-80).
 *
 * The URL stays the source of truth for the page that is open. This module
 * remembers the last filter query and pagination per page so that:
 *  - the sidebar links re-open a page with its previous state (keepalive);
 *  - the board and the work item list share one filter query, so changing a
 *    filter in either page applies to the other on the next visit.
 *
 * Only explicitly present filter params are stored. A page's own defaults
 * (`rootOnly` differs between board and list, `/issues` pins `kind`) therefore
 * keep working: an absent param means "use this page's default".
 */

export type WorkView = "board" | "backlog" | "issues";

/** Filter params shared by the toolbar; `page`/`view` stay page-local. */
const FILTER_KEYS = [
  "sprint",
  "kind",
  "subtype",
  "rootOnly",
  "hasChildren",
  "completed",
  "status",
  "assignee",
  "participant",
  "q",
  "order",
] as const;

interface BacklogExtras {
  page: number;
  view: "" | "tree" | "flat";
}

interface ProjectViewMemory {
  /** Filter query shared by the board and the work item list. */
  shared: string;
  /** The issues page is pinned to `kind=issue`, so it keeps its own filters. */
  issues: string;
  backlog: BacklogExtras;
  issuesPage: BacklogExtras;
}

const STORAGE_PREFIX = "rdm.work-item-views.";

const EMPTY: ProjectViewMemory = {
  shared: "",
  issues: "",
  backlog: { page: 1, view: "" },
  issuesPage: { page: 1, view: "" },
};

const cache = new Map<string, ProjectViewMemory>();
let version = 0;
const listeners = new Set<() => void>();

function storageKey(projectKey: string): string {
  return `${STORAGE_PREFIX}${projectKey}`;
}

function load(projectKey: string): ProjectViewMemory {
  const cached = cache.get(projectKey);
  if (cached) return cached;
  let stored: ProjectViewMemory = EMPTY;
  try {
    const raw = sessionStorage.getItem(storageKey(projectKey));
    if (raw) stored = { ...EMPTY, ...(JSON.parse(raw) as Partial<ProjectViewMemory>) };
  } catch {
    // Private mode / corrupt value: start from the defaults.
  }
  cache.set(projectKey, stored);
  return stored;
}

function save(projectKey: string, value: ProjectViewMemory): void {
  cache.set(projectKey, value);
  try {
    sessionStorage.setItem(storageKey(projectKey), JSON.stringify(value));
  } catch {
    // Keep the in-memory value when storage is unavailable.
  }
  version += 1;
  listeners.forEach((listener) => listener());
}

/** Explicit filter params, in a stable order (page/view excluded). */
export function filterQuery(params: URLSearchParams): string {
  const out = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value !== null && value !== "") out.set(key, value);
  }
  return out.toString();
}

function readExtras(params: URLSearchParams): BacklogExtras {
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);
  const rawView = params.get("view");
  return {
    page,
    view: rawView === "tree" || rawView === "flat" ? rawView : "",
  };
}

function sameExtras(a: BacklogExtras, b: BacklogExtras): boolean {
  return a.page === b.page && a.view === b.view;
}

export function rememberViewSearch(
  projectKey: string,
  view: WorkView,
  params: URLSearchParams,
): void {
  const current = load(projectKey);
  const filters = filterQuery(params);
  let next = current;

  if (view === "issues") {
    const extras = readExtras(params);
    if (current.issues === filters && sameExtras(current.issuesPage, extras)) return;
    next = { ...current, issues: filters, issuesPage: extras };
  } else {
    const extras = view === "backlog" ? readExtras(params) : current.backlog;
    const filtersChanged = current.shared !== filters;
    // A filter change makes the old backlog page offset meaningless; keep the
    // view mode but go back to the first page.
    const nextExtras: BacklogExtras =
      view === "backlog"
        ? extras
        : filtersChanged
          ? { ...current.backlog, page: 1 }
          : current.backlog;
    if (!filtersChanged && sameExtras(current.backlog, nextExtras)) return;
    next = { ...current, shared: filters, backlog: nextExtras };
  }
  save(projectKey, next);
}

function withExtras(search: string, extras: BacklogExtras): string {
  const params = new URLSearchParams(search);
  if (extras.view) params.set("view", extras.view);
  if (extras.page > 1) params.set("page", String(extras.page));
  return params.toString();
}

/** Sidebar target for a work item page, carrying the remembered state. */
export function viewPath(projectKey: string, view: WorkView): string {
  const memory = load(projectKey);
  const base = `/projects/${projectKey}/${view}`;
  if (view === "issues") {
    const search = withExtras(memory.issues, memory.issuesPage);
    return search ? `${base}?${search}` : base;
  }
  if (view === "board") {
    return memory.shared ? `${base}?${memory.shared}` : base;
  }
  const search = withExtras(memory.shared, memory.backlog);
  return search ? `${base}?${search}` : base;
}

export function subscribeViewMemory(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function viewMemoryVersion(): number {
  return version;
}

export function clearViewMemory(): void {
  cache.clear();
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith(STORAGE_PREFIX)) sessionStorage.removeItem(key);
    }
  } catch {
    // Storage unavailable: the in-memory cache is already cleared.
  }
  version += 1;
  listeners.forEach((listener) => listener());
}

/** Keep the store in sync with the page's effective list URL. */
export function useWorkItemViewMemory(projectKey: string, view: WorkView): void {
  const [searchParams] = useListSearchParams();
  const search = searchParams.toString();
  useEffect(() => {
    rememberViewSearch(projectKey, view, new URLSearchParams(search));
  }, [projectKey, view, search]);
}
