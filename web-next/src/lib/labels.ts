// Single place for human labels of wire-level enums. Backend DTOs keep the
// stable English values; only presentation is localized here.

export const STATUS_LABELS: Record<string, string> = {
  // shared / tasks / epics
  TODO: "待办",
  IN_PROGRESS: "进行中",
  BLOCKED: "阻塞",
  TO_REVIEW: "待评审",
  IN_REVIEW: "评审中",
  TO_TEST: "待测试",
  DONE: "完成",
  PUBLISHED: "已发布",
  CANCELLED: "已取消",
  // issues
  OPEN: "打开",
  TO_CONFIRM: "待确认",
  TO_FIX: "待修复",
  FIXING: "修复中",
  CLOSED_DONE: "已关闭",
  CLOSED_REJECTED: "已驳回",
  REOPEN: "重新打开",
  // sprints
  PLANNED: "计划中",
  ACTIVE: "进行中",
  CLOSED: "已关闭",
  // steps / executors
  PENDING: "待执行",
  COMPLETED: "已完成",
  REJECTED: "已拒绝",
  // misc
  ARCHIVED: "已归档",
};

export const STEP_MODE_LABELS: Record<string, string> = {
  direct: "直接执行",
  approval: "审批",
  task: "任务",
};

export const ROLE_LABELS: Record<string, string> = {
  project_owner: "项目经理",
  manager: "管理员",
  sprint_manager: "迭代经理",
  worker: "成员",
  org_owner: "组织所有者",
  user_manager: "用户管理员",
  project_director: "项目总监",
};

export const SEVERITY_LABELS: Record<string, string> = {
  blocker: "阻断",
  critical: "严重",
  major: "主要",
  minor: "次要",
  trivial: "轻微",
};

export const KIND_LABELS: Record<string, string> = {
  epic: "Epic",
  story: "需求",
  issue: "缺陷",
  task: "任务",
};

export const ARTIFACT_KIND_LABELS: Record<string, string> = {
  link: "链接",
  doc: "文档",
  design: "设计稿",
  api_doc: "API 文档",
  repo: "代码仓库",
  other: "其他",
};

export const WORKSPACE_KIND_LABELS: Record<string, string> = {
  git_repo: "代码仓库",
  doc_repo: "文档仓库",
  design: "设计资源",
  other: "其他",
};

export const ATTACHMENT_STATE_LABELS: Record<string, string> = {
  temp: "草稿",
  active: "已提交",
};

export const OUTBOX_STATUS_LABELS: Record<string, string> = {
  pending: "待投递",
  delivering: "投递中",
  delivered: "已送达",
  failed: "失败",
};

/** Fallback for custom subtype states: "WAITING_QA" -> "等待 QA". */
export function prettify(value: string): string {
  const text = value.replace(/_/g, " ").trim();
  if (!text) return value;
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? prettify(status);
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? prettify(role);
}

export function severityLabel(severity: string): string {
  return SEVERITY_LABELS[severity] ?? prettify(severity);
}

export function stepModeLabel(mode: string): string {
  return STEP_MODE_LABELS[mode] ?? prettify(mode);
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? prettify(kind);
}

export function artifactKindLabel(kind: string): string {
  return ARTIFACT_KIND_LABELS[kind] ?? prettify(kind);
}

export function workspaceKindLabel(kind: string): string {
  return WORKSPACE_KIND_LABELS[kind] ?? prettify(kind);
}
