import { KIND_VALUES } from "./constants";

/**
 * Shared filter/sort state for the work item list and board (RDM-63).
 *
 * The URL stays the source of truth: pages parse it with `parseFilters` and
 * write patches through `applyFilterPatch`, so filters survive opening the
 * item drawer and are shareable. Defaults differ per page (list vs board
 * `rootOnly`, `/issues` pinned kinds) and are passed in by the caller.
 */

export const DEFAULT_KINDS: readonly string[] = ["story", "issue", "task"];
export const ALL_KINDS_PARAM = "all";

export type WorkItemOrder = "composite" | "created_desc" | "created_asc";
export type CompletedFilter = "" | "true" | "false";
export type HasChildrenFilter = "" | "true" | "false";

export interface WorkItemFilters {
  sprint: string;
  /** Empty means every kind; the default selection is story+issue+task. */
  kinds: string[];
  subtypes: string[];
  rootOnly: boolean;
  /** Empty means "no constraint"; true=has children, false=no children. */
  hasChildren: HasChildrenFilter;
  completed: CompletedFilter;
  statuses: string[];
  assignees: string[];
  participants: string[];
  q: string;
  order: WorkItemOrder;
}

export interface FilterDefaults {
  kinds: readonly string[];
  rootOnly: boolean;
}

function csv(value: string | null): string[] {
  return value ? value.split(",").filter(Boolean) : [];
}

export function parseFilters(
  params: URLSearchParams,
  defaults: FilterDefaults,
): WorkItemFilters {
  const kindParam = params.get("kind");
  // `kind=all` is the explicit "every type" selection; absence means defaults.
  const kinds =
    kindParam === ALL_KINDS_PARAM
      ? []
      : kindParam
        ? csv(kindParam)
        : [...defaults.kinds];
  const orderParam = params.get("order");
  const order: WorkItemOrder =
    orderParam === "created_asc" || orderParam === "created_desc"
      ? orderParam
      : "composite";
  const rootParam = params.get("rootOnly");
  const rootOnly = rootParam === null ? defaults.rootOnly : rootParam !== "false";
  const completedParam = params.get("completed");
  const completed: CompletedFilter =
    completedParam === "true" || completedParam === "false" ? completedParam : "";
  const hasChildrenParam = params.get("hasChildren");
  const hasChildren: HasChildrenFilter =
    hasChildrenParam === "true" || hasChildrenParam === "false" ? hasChildrenParam : "";
  return {
    sprint: params.get("sprint") ?? "",
    kinds,
    subtypes: csv(params.get("subtype")),
    rootOnly,
    hasChildren,
    completed,
    statuses: csv(params.get("status")),
    assignees: csv(params.get("assignee")),
    participants: csv(params.get("participant")),
    q: params.get("q") ?? "",
    order,
  };
}

function setOrDelete(params: URLSearchParams, key: string, value: string | null) {
  if (value === null || value === "") params.delete(key);
  else params.set(key, value);
}

function orderedKinds(kinds: string[]): string[] {
  return KIND_VALUES.filter((kind) => kinds.includes(kind));
}

/**
 * Apply a filter patch to the list URL. Any change resets pagination, since a
 * page offset from the previous result set is meaningless.
 */
export function applyFilterPatch(
  params: URLSearchParams,
  patch: Partial<WorkItemFilters>,
  defaults: FilterDefaults,
): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const [key, value] of Object.entries(patch)) {
    switch (key) {
      case "sprint":
        setOrDelete(next, "sprint", (value as string) || null);
        break;
      case "kinds": {
        const kinds = orderedKinds(value as string[]);
        if (kinds.length === 0) next.set("kind", ALL_KINDS_PARAM);
        else if (kinds.join(",") === orderedKinds([...defaults.kinds]).join(",")) {
          next.delete("kind");
        } else next.set("kind", kinds.join(","));
        break;
      }
      case "subtypes":
        setOrDelete(next, "subtype", (value as string[]).join(","));
        break;
      case "rootOnly":
        if ((value as boolean) === defaults.rootOnly) next.delete("rootOnly");
        else next.set("rootOnly", value ? "true" : "false");
        break;
      case "hasChildren":
        setOrDelete(next, "hasChildren", (value as HasChildrenFilter) || null);
        break;
      case "completed":
        setOrDelete(next, "completed", (value as CompletedFilter) || null);
        break;
      case "statuses":
        setOrDelete(next, "status", (value as string[]).join(","));
        break;
      case "assignees":
        setOrDelete(next, "assignee", (value as string[]).join(","));
        break;
      case "participants":
        setOrDelete(next, "participant", (value as string[]).join(","));
        break;
      case "q":
        setOrDelete(next, "q", ((value as string) || "").trim() || null);
        break;
      case "order":
        if (value === "composite") next.delete("order");
        else next.set("order", value as string);
        break;
      default:
        break;
    }
  }
  next.delete("page");
  return next;
}

/**
 * Query params for `GET /projects/{key}/work-items` (and the facets endpoint).
 * `order=composite` is always sent because it is not the server-side default
 * (other consumers still rely on the legacy display_no order).
 */
export function buildRequestParams(filters: WorkItemFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.kinds.length > 0) {
    const kinds = orderedKinds(filters.kinds);
    if (kinds.length !== KIND_VALUES.length) params.set("kind", kinds.join(","));
  }
  if (filters.subtypes.length > 0) params.set("subtype", filters.subtypes.join(","));
  if (filters.sprint) params.set("sprint", filters.sprint);
  if (filters.rootOnly) params.set("root_only", "true");
  if (filters.hasChildren) params.set("has_children", filters.hasChildren);
  if (filters.completed) params.set("completed", filters.completed);
  if (filters.statuses.length > 0) params.set("status", filters.statuses.join(","));
  if (filters.assignees.length > 0) params.set("assignee", filters.assignees.join(","));
  if (filters.participants.length > 0) {
    params.set("participant", filters.participants.join(","));
  }
  if (filters.q) params.set("q", filters.q);
  params.set("order", filters.order);
  return params;
}
