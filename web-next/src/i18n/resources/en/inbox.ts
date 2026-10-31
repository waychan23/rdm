const inbox = {
  title: "Notifications / To-dos",
  tabs: {
    notifications: "Notifications",
    todo: "To-dos",
  },
  sort: {
    newest: "Newest first",
    oldest: "Oldest first",
  },
  filters: {
    unreadOnly: "Unread only",
  },
  actions: {
    markAllRead: "Mark all read",
    refresh: "Refresh",
  },
  empty: {
    unreadHeader: "No unread notifications",
    header: "No notifications",
    description: "Assignments, step and comment notifications will appear here.",
  },
  notify: {
    markReadFailed: "Failed to mark as read",
    markAllSuccess: "Marked {{count}} as read",
    markAllFailed: "Failed to mark notifications",
    openItemFailed: "Cannot open work item",
    openItemMissingProject: "Missing project information. Refresh and try again.",
  },
  todo: {
    approvals: "Awaiting my approval ({{count}})",
    approvalsEmpty: "No steps awaiting approval",
    pendingSteps: "Steps awaiting my action ({{count}})",
    pendingStepsEmpty: "No pending steps",
    assigned: "My work items ({{count}})",
    assignedEmpty: "No work items assigned to you",
    overdue: "Overdue ({{count}})",
    overdueEmpty: "No overdue work items",
    mode: {
      approval: "Approval",
      execute: "Execute",
    },
    due: "Due {{date}}",
  },
};

export default inbox;
