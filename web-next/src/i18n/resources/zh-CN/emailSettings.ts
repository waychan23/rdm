const emailSettings = {
  title: "邮件设置",
  subtitle:
    "配置系统对外发信的 SMTP 服务器和发信人。仅组织 Owner 与用户管理员可管理；密码加密保存，不回显。",
  sections: {
    server: "SMTP 服务器",
    sender: "发信人",
    test: "发送测试邮件",
  },
  fields: {
    enabled: "启用外部邮件",
    smtpHost: "SMTP 主机",
    smtpPort: "端口",
    security: "加密方式",
    username: "用户名",
    password: "密码",
    fromAddress: "发信人地址",
    fromName: "发信人名称",
    testTo: "测试收件人",
  },
  security: {
    none: "不加密",
    starttls: "STARTTLS",
    ssl: "SSL/TLS",
  },
  password: {
    saved: "已保存密码；留空保持不变",
    empty: "未设置密码",
    set: "填写新密码",
    clear: "清除已保存的密码",
  },
  hint: "信箱发信时，收件人中格式为邮箱地址的条目会通过这里配置的服务器发出；项目成员与 group 仍走站内信箱。",
  actions: {
    save: "保存",
    saving: "保存中…",
    test: "发送测试邮件",
    testing: "发送中…",
  },
  notify: {
    saved: "邮件设置已保存",
    saveFailed: "保存失败",
    loadFailed: "加载失败",
    testSent: "测试邮件已发送到 {{to}}",
    testFailed: "测试邮件发送失败",
  },
};

export default emailSettings;
