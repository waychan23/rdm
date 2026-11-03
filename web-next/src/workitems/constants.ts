import { i18n } from "../i18n";
import { kindLabel, severityLabel } from "../lib/labels";

export interface KindOption {
  value: string;
  label: string;
}

export const KIND_VALUES = ["epic", "story", "issue", "task"] as const;

/** Mirrors the backend `_SPRINT_ITEM_KINDS` rule (§17.3, §16.31). */
export const SPRINT_ITEM_KINDS: ReadonlySet<string> = new Set(["story", "issue", "task"]);

export function kindOptions(): KindOption[] {
  return KIND_VALUES.map((value) => ({ value, label: kindLabel(value) }));
}

export function severityOptions(): { value: string; label: string }[] {
  return ["blocker", "critical", "major", "minor", "trivial"].map((value) => ({
    value,
    label: severityLabel(value),
  }));
}

export function taskTypeOptions(): { value: string; label: string }[] {
  return [
    "other",
    "frontend",
    "backend",
    "fullstack",
    "code_review",
    "testing",
    "test_case_design",
    "docs",
    "ui_design",
    "product_design",
    "release",
  ].map((value) => ({
    value,
    label: String(i18n.t(`taskType.${value}` as never, { ns: "labels" })),
  }));
}

export const PAGE_SIZE = 20;
// Board columns paginate independently and keep their own scroll offset; a
// smaller page avoids over-fetching while the column scrolls in more rows.
export const BOARD_COLUMN_PAGE_SIZE = 10;
