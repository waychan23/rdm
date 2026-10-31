const mailbox = {
  title: {
    default: "信箱",
    withProject: "信箱 · {{project}}",
  },
  folder: {
    inbox: "收件箱",
    archived: "已归档",
    sent: "已发送",
  },
  sort: {
    newest: "最新在前",
    oldest: "最早在前",
  },
  view: {
    flat: "平铺",
    thread: "会话",
  },
  filters: {
    unreadOnly: "仅未读",
  },
  actions: {
    markRead: "标已读",
    markSelectedRead: "标记已读",
    archive: "归档",
    unarchive: "移回收件箱",
    delete: "删除",
    reply: "回复",
    loadMore: "加载更多",
    compose: "发信",
    groups: "群信箱",
    createGroup: "创建群信箱",
    cancel: "取消",
    send: "发送",
    close: "关闭",
  },
  fields: {
    recipients: "收件人",
    subject: "主题",
    body: "正文（Markdown）",
    groupName: "名称",
    members: "成员",
  },
  placeholders: {
    allProjects: "全部项目",
    allIdentities: "全部身份",
    search: "搜索主题/正文",
    selectRecipients: "选择成员或群信箱",
    selectMembers: "选择成员",
  },
  empty: {
    header: "没有信件",
    description: "有新站内信时会出现在这里。",
  },
  message: {
    recipients: "收件人：{{names}}",
    refs: "关联：",
  },
  thread: {
    count: "{{count}} 封",
    expand: "展开",
    collapse: "折叠",
  },
  owner: {
    mine: "我的信箱",
    agent: "{{name}}（agent）",
    unknown: "未知身份",
  },
  identity: {
    me: "我（{{name}}）",
    agent: "{{name}}（agent）",
  },
  compose: {
    replyTitle: "回复信件",
    newTitle: "发站内信",
  },
  group: {
    title: "群信箱",
    description:
      "群信箱用于一次投递给多个成员；成员仍会各自收到一份站内信。",
    none: "还没有群信箱",
    noMembers: "无成员",
    option: "{{name}}（群信箱）",
  },
  notify: {
    markFailed: "标记失败",
    archived: "已归档",
    unarchived: "已移回收件箱",
    archiveFailed: "归档失败",
    deleted: "已删除",
    deleteFailed: "删除失败",
    loadGroupsFailed: "加载群信箱失败",
    selectProject: "请先在顶部选择项目",
    selectProjectToSend: "请先在顶部选择项目后再发信",
    groupNameRequired: "群信箱名称必填",
    groupCreated: "已创建群信箱",
    createFailed: "创建失败",
    recipientsRequired: "收件人、主题、正文均必填",
    replied: "已回复",
    sent: "已发送",
    sendFailed: "发送失败",
  },
  listSeparator: "、",
};

export default mailbox;
