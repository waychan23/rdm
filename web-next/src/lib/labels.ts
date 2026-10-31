import { i18n } from "../i18n";

/** Fallback for custom subtype states: "WAITING_QA" -> "Waiting qa". */
export function prettify(value: string): string {
  const text = value.replace(/_/g, " ").trim();
  if (!text) return value;
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

function label(group: string, value: string): string {
  const key = `${group}.${value}`;
  return i18n.exists(key as never, { ns: "labels" })
    ? String(i18n.t(key as never, { ns: "labels" }))
    : prettify(value);
}

export function statusLabel(status: string): string {
  return label("status", status);
}

export function roleLabel(role: string): string {
  return label("role", role);
}

export function severityLabel(severity: string): string {
  return label("severity", severity);
}

export function stepModeLabel(mode: string): string {
  return label("stepMode", mode);
}

export function kindLabel(kind: string): string {
  return label("kind", kind);
}

export function kindShortLabel(kind: string): string {
  return label("kindShort", kind);
}

export function artifactKindLabel(kind: string): string {
  return label("artifactKind", kind);
}

export function workspaceKindLabel(kind: string): string {
  return label("workspaceKind", kind);
}

export function attachmentStateLabel(state: string): string {
  return label("attachmentState", state);
}

export function outboxStatusLabel(status: string): string {
  return label("outboxStatus", status);
}

export function notificationTypeLabel(type: string): string {
  return label("notificationType", type);
}

export function searchTypeLabel(type: string): string {
  return label("searchType", type);
}
