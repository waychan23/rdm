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
  { value: "other", label: "其他" },
  { value: "frontend", label: "前端开发" },
  { value: "backend", label: "后端开发" },
  { value: "fullstack", label: "全栈开发" },
  { value: "code_review", label: "代码评审" },
  { value: "testing", label: "测试" },
  { value: "test_case_design", label: "测试用例设计" },
  { value: "docs", label: "文档编写" },
  { value: "ui_design", label: "UI设计" },
  { value: "product_design", label: "产品设计" },
  { value: "release", label: "系统发布" },
];

export const PAGE_SIZE = 20;
