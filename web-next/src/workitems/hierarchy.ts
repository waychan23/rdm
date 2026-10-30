import type { WorkItem } from "../types";

export interface WorkItemRow {
  item: WorkItem;
  depth: number;
  childCount: number;
  collapsed: boolean;
}

export interface WorkItemTreePage {
  rows: WorkItemRow[];
  /** Number of top-level rows, used for the pager. */
  rootCount: number;
  pageCount: number;
}

/**
 * Flatten one page of the filtered work items into collapsible tree rows.
 *
 * `items` is expected in server order (display_no ascending) and already
 * filtered; children keep that order under their parent. Items whose parent is
 * not part of the filtered set are treated as roots, so a filter (kind,
 * assignee, search…) never hides a matching row.
 *
 * Pagination applies to root rows: a page always carries the full subtree of
 * the roots on it, otherwise the hierarchy would be misleading.
 */
export function buildWorkItemTree(
  items: WorkItem[],
  collapsed: ReadonlySet<string>,
  page: number,
  pageSize: number,
): WorkItemTreePage {
  const present = new Set(items.map((item) => item.id));
  const childrenOf = new Map<string, WorkItem[]>();
  const roots: WorkItem[] = [];

  for (const item of items) {
    if (item.parent_id && present.has(item.parent_id)) {
      const siblings = childrenOf.get(item.parent_id);
      if (siblings) siblings.push(item);
      else childrenOf.set(item.parent_id, [item]);
    } else {
      roots.push(item);
    }
  }

  // Defensive: the domain forbids cycles. If bad data ever forms one, promote
  // the unreachable nodes to roots instead of silently dropping them.
  const reachable = new Set<string>();
  const mark = (item: WorkItem) => {
    if (reachable.has(item.id)) return;
    reachable.add(item.id);
    for (const child of childrenOf.get(item.id) ?? []) mark(child);
  };
  roots.forEach(mark);
  for (const item of items) {
    if (!reachable.has(item.id)) {
      roots.push(item);
      mark(item);
    }
  }

  const pageCount = Math.max(1, Math.ceil(roots.length / pageSize));
  const start = Math.max(0, (page - 1) * pageSize);
  const pageRoots = roots.slice(start, start + pageSize);

  const rows: WorkItemRow[] = [];
  const seen = new Set<string>();
  const walk = (item: WorkItem, depth: number) => {
    if (seen.has(item.id)) return;
    seen.add(item.id);
    const children = childrenOf.get(item.id) ?? [];
    const isCollapsed = children.length > 0 && collapsed.has(item.id);
    rows.push({ item, depth, childCount: children.length, collapsed: isCollapsed });
    if (!isCollapsed) {
      for (const child of children) walk(child, depth + 1);
    }
  };
  for (const root of pageRoots) walk(root, 0);

  return { rows, rootCount: roots.length, pageCount };
}
