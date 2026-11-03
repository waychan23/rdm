# 安全策略

## 报告漏洞

请**不要**通过公开 issue 报告安全问题。使用 GitHub 的私密渠道：

- [Security Advisories](https://github.com/waychan23/rdm/security/advisories/new)

请在报告中包含：受影响版本、复现步骤、影响范围，以及（如可能）修复建议。
我们会在确认后尽快回复并协调披露。

## 支持范围

项目当前处于 0.x（Beta）阶段，只为最新发布版本提供安全修复。

## 安全边界

rdm 面向**单组织、自托管**部署，默认安全假设如下：

- `rdm serve` 只允许绑定回环地址，必须由 nginx 等反向代理对外提供 TLS。
- Web 认证是无状态 OAuth（Auth Code + PKCE）；CLI 使用 PAT。PAT 只能由本人创建，
  可指定 `act_as` 自己管理的 agent；管理员只能撤销，不能代签。
- 附件下载使用短时效签名 URL；数据目录内的 `webhook-secret`、`attachment-secret`
  是 HMAC 密钥，应按敏感数据保护。
- 部署时请封禁 `/api/v1/local/`（nginx 样例已包含），并按需限制 `/api/docs`。

发现配置或文档与以上假设不符，也欢迎通过上述渠道报告。
