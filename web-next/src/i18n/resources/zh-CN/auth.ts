const auth = {
  login: {
    title: "rd-manager 登录",
    username: "用户名",
    usernamePlaceholder: "请输入用户名",
    password: "密码",
    remember: "记住我（7 天内免登录）",
    submit: "登录",
    bootstrapHint:
      "首次部署请使用服务启动日志中的 bootstrap-url 设置 Org Owner 密码；忘记密码可由部署主机执行 rdm account recover-owner 重新生成。",
    redirecting: "正在跳转到登录…",
    failed: "登录失败",
  },
  callback: {
    title: "登录未完成",
    retry: "重新登录",
    completing: "正在完成登录…",
    errors: {
      missingCode: "缺少授权码或状态参数。",
      invalidCallback: "登录回调无效，请重试。",
    },
  },
  setPassword: {
    missingTicket: {
      title: "链接无效",
      body: "缺少 ticket 参数，请向管理员重新索取设置密码链接。",
    },
    checking: "正在校验链接…",
    checkFailed: {
      title: "无法校验链接状态",
      body: "网络或服务异常，请稍后重试。",
    },
    retry: "重试",
    form: {
      title: "设置密码",
      hint: "密码长度 8–128 位，请妥善保管。",
      newPassword: "新密码",
      confirmPassword: "确认新密码",
      submit: "保存",
    },
    invalid: {
      consumed: {
        title: "该链接已失效",
        body: "链接已被使用，或已因重新生成而失效。",
      },
      expired: {
        title: "该链接已过期",
        body: "设置密码链接已失效。",
      },
      userMissing: {
        title: "链接无效",
        body: "该链接对应的用户已不可用。",
      },
      notFound: {
        title: "链接无效",
        body: "链接不存在或已被替换。",
      },
      nextStep: {
        bootstrap:
          "请查看服务启动日志中的 bootstrap-url，或由管理员执行 rdm account recover-owner 重新生成。",
        fallback: "请向管理员重新索取设置密码链接后再试。",
      },
    },
    done: {
      title: "密码已设置",
      successTitle: "完成",
      successBody: "现在用新密码登录。",
      gotoLogin: "去登录",
    },
    errors: {
      mismatch: "两次输入的密码不一致",
      failed: "设置密码失败",
    },
  },
  consent: {
    error: {
      title: "授权不可用",
      hint: "授权链接有效期 10 分钟且只能使用一次，请回到终端重新发起登录。",
    },
    loading: "加载授权请求…",
    title: "授权访问 rdm",
    request: "应用 <bold>{client}</bold> 请求访问你的 rdm 工作区（scope: {scopes}）。",
    identityPrompt: "以哪个身份授权",
    managedByHuman: "受管于人类账号",
    deny: "拒绝",
    allow: "允许",
  },
};

export default auth;
