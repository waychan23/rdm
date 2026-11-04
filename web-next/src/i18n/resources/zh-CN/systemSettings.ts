const systemSettings = {
  title: "系统设置",
  subtitle: "组织级配置，对所有项目生效。",
  hint: "Web 前台站点用于决定 Agent 对话消息、邮件中提供的工作项链接打开的站点。链接域名优先级：项目 .rdm/project.json > 用户 ~/.rdm/config.json > 此处组织设置 > 默认（MCP 服务同源）。",
  sections: {
    webOrigin: "Web 前台站点",
  },
  fields: {
    webOrigin: "Web 前台站点",
    webOriginHint:
      "决定 Agent 对话消息、邮件中提供的工作项链接打开的站点。不填写时使用默认地址。",
    webOriginPlaceholder: "例如 https://rdm.example.com",
    fallback: "当前默认地址：{{origin}}",
  },
  actions: {
    save: "保存",
    saving: "保存中…",
    useCurrentOrigin: "使用当前页面地址",
  },
  notify: {
    saved: "系统设置已保存。",
    saveFailed: "保存系统设置失败",
  },
};

export default systemSettings;
