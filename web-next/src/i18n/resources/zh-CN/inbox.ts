const inbox = {
  title: "通知/待办",
  tabs: {
    notifications: "通知",
    todo: "待办",
  },
  sort: {
    newest: "最新在前",
    oldest: "最早在前",
  },
  filters: {
    unreadOnly: "只看未读",
  },
  actions: {
    markAllRead: "全部已读",
    refresh: "刷新",
  },
  empty: {
    unreadHeader: "没有未读通知",
    header: "暂无通知",
    description: "指派、步骤与评论通知会出现在这里。",
  },
  notify: {
    markReadFailed: "标记已读失败",
    markAllSuccess: "已标记 {{count}} 条为已读",
    markAllFailed: "标记失败",
    openItemFailed: "无法打开工作项",
    openItemMissingProject: "缺少所属项目信息，请刷新后重试。",
  },
  todo: {
    approvals: "待我审批（{{count}}）",
    approvalsEmpty: "没有待审批步骤",
    pendingSteps: "待我执行的步骤（{{count}}）",
    pendingStepsEmpty: "没有待执行步骤",
    assigned: "我的工作项（{{count}}）",
    assignedEmpty: "没有分配给你的工作项",
    overdue: "逾期（{{count}}）",
    overdueEmpty: "没有逾期工作项",
    mode: {
      approval: "审批",
      execute: "执行",
    },
    due: "截止 {{date}}",
  },
};

export default inbox;
