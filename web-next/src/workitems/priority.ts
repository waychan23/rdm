import { token } from "@atlaskit/tokens";

// Lower numbers mean higher priority (P-level convention). Priority is
// mandatory: every work item has one of these four levels.
export interface PriorityOption {
  value: number;
  label: string;
  color: string;
}

export const DEFAULT_PRIORITY = 3;

export const PRIORITY_OPTIONS: PriorityOption[] = [
  { value: 1, label: "紧急", color: token("color.icon.danger") },
  { value: 2, label: "高", color: token("color.icon.warning") },
  { value: 3, label: "中", color: token("color.icon.information") },
  { value: 4, label: "低", color: token("color.icon.disabled") },
];

/** Normalize legacy/unexpected values to the medium level. */
export function priorityOption(value: number | null | undefined): PriorityOption {
  return (
    PRIORITY_OPTIONS.find((option) => option.value === value) ??
    PRIORITY_OPTIONS[2]
  );
}

export function priorityLabel(value: number | null | undefined): string {
  return priorityOption(value).label;
}

export function priorityColor(value: number | null | undefined): string {
  return priorityOption(value).color;
}
