import { token } from "@atlaskit/tokens";

import { i18n } from "../i18n";

// Lower numbers mean higher priority (P-level convention). Priority is
// mandatory: every work item has one of these four levels.
export interface PriorityOption {
  value: number;
  label: string;
  color: string;
}

export const DEFAULT_PRIORITY = 3;

const PRIORITY_COLORS: Record<number, string> = {
  1: token("color.icon.danger"),
  2: token("color.icon.warning"),
  3: token("color.icon.information"),
  4: token("color.icon.disabled"),
};

export function priorityLabel(value: number | null | undefined): string {
  return String(
    i18n.t(`priority.${value ?? DEFAULT_PRIORITY}` as never, { ns: "labels" }),
  );
}

/** Built at call time so labels follow the current language. */
export function priorityOptions(): PriorityOption[] {
  return [1, 2, 3, 4].map((value) => ({
    value,
    label: priorityLabel(value),
    color: PRIORITY_COLORS[value],
  }));
}

/** Normalize legacy/unexpected values to the medium level. */
export function priorityOption(value: number | null | undefined): PriorityOption {
  const normalized = value !== null && value !== undefined && PRIORITY_COLORS[value] ? value : DEFAULT_PRIORITY;
  return {
    value: normalized,
    label: priorityLabel(normalized),
    color: PRIORITY_COLORS[normalized],
  };
}

export function priorityColor(value: number | null | undefined): string {
  return priorityOption(value).color;
}
