// Mirrors the backend rules in workitem_service (_ALLOWED_PARENT). The detail
// meta `allowed_parent_kinds` / `allowed_child_kinds` is authoritative once
// loaded; these constants cover the create dialog before a detail exists.

export const ALLOWED_PARENT_KINDS: Record<string, string[]> = {
  epic: [],
  story: ["epic"],
  issue: ["story", "task"],
  task: ["epic", "story", "issue", "task"],
};

export const ALLOWED_CHILD_KINDS: Record<string, string[]> = {
  epic: ["story", "task"],
  // Keep "task" first so child dialogs still default to a task.
  story: ["task", "issue"],
  issue: ["task"],
  task: ["task", "issue"],
};

export function allowedParentKinds(kind: string): string[] {
  return ALLOWED_PARENT_KINDS[kind] ?? [];
}

export function allowedChildKinds(kind: string): string[] {
  return ALLOWED_CHILD_KINDS[kind] ?? [];
}

export function defaultChildKind(kind: string): string | null {
  return allowedChildKinds(kind)[0] ?? null;
}
