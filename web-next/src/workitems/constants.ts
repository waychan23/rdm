export interface KindOption {
  value: string;
  label: string;
}

export const KIND_OPTIONS: KindOption[] = [
  { value: "epic", label: "Epic" },
  { value: "story", label: "需求" },
  { value: "issue", label: "缺陷" },
  { value: "task", label: "任务" },
];

export const SEVERITY_OPTIONS = ["blocker", "critical", "major", "minor", "trivial"].map(
  (value) => ({ label: value, value }),
);

export const TASK_TYPE_OPTIONS = [
  "product_design",
  "ux_design",
  "frontend",
  "backend",
  "fullstack",
  "qa",
  "release",
  "docs",
  "other",
].map((value) => ({ label: value, value }));

export const PAGE_SIZE = 20;
