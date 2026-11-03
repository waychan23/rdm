# 配置参考

所有服务端配置通过环境变量 `RDM_*` 提供（pydantic-settings）。应用**不会自动读取 `.env`**：
请在 shell 中 export，或用 systemd `EnvironmentFile` / 容器环境变量注入。
模板见仓库根 [.env.example](../.env.example) 与 [deploy/systemd/rdm.env.example](../deploy/systemd/rdm.env.example)。

## 服务端

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RDM_DATA_DIR` | `~/rdm-data` | 数据目录：SQLite 数据库、项目文件、workflow 配置、HMAC 密钥 |
| `RDM_DATABASE_URL` | 空 | 为空时用 `<data-dir>/rdm.db`；支持 `postgresql://`（psycopg 3）与 `sqlite://`。必须带 `pg_search` 扩展才能用 PG 全文搜索 |
| `RDM_HOST` | `127.0.0.1` | 绑定地址。企业内网/容器部署可设 `0.0.0.0` 或内网 IP，但必须同时设置 `RDM_PUBLIC_BASE_URL`；`/api/v1/local/*` 仍仅限本机回环 |
| `RDM_PORT` | `8765` | 监听端口 |
| `RDM_PUBLIC_BASE_URL` | 空（回落到绑定地址） | 浏览器/MCP 客户端使用的公网 origin，无路径。非回环必须 `https://` |
| `RDM_EXTRA_REDIRECT_URIS` | 空 | 额外允许的 OAuth 回环 redirect URI，逗号分隔（测试用） |
| `RDM_ATTACHMENT_MAX_BYTES` | `20971520`（20 MB） | 附件大小上限 |
| `RDM_WEBHOOK_POLL_SECONDS` | `2.0` | Webhook 发送队列轮询间隔 |
| `RDM_WEBHOOK_TIMEOUT_SECONDS` | `5.0` | 单次投递超时 |
| `RDM_WEBHOOK_BACKOFF` | `60,300,900` | 失败重试退避（秒，逗号分隔） |

`RDM_DATABASE_URL` 的兼容处理：`postgres://`、`postgresql://`、`postgresql+psycopg2://` 会规范化为
`postgresql+psycopg://`；`asyncpg` URL 不受支持，会直接报错。

## CLI 客户端

| 变量 | 说明 |
|---|---|
| `RDM_SERVER_URL` | 服务地址（等价于 `--url`），默认 `http://127.0.0.1:8765` |
| `RDM_TOKEN` | Bearer PAT；`rdm integrate mcp --method token` 生成的项目级配置常用 |
| `RDM_PROJECT` | 默认项目 key，免去每次传 `--project` |

## 测试

| 变量 | 说明 |
|---|---|
| `RDM_TEST_BACKEND` | `sqlite`（默认）/ `postgres` / `both` |
| `RDM_TEST_DB_URL` | 复用已有 PostgreSQL 时指定；缺省用 testcontainers 起 ParadeDB |

## 数据目录布局

```
<data-dir>/
├── rdm.db                  # SQLite 数据库（使用 PostgreSQL 时不存在）
├── projects/<id>/          # 项目文件：docs、skills、attachments
├── workflow-configs/       # 可编辑的 workflow JSON5（首启复制包内默认定义）
├── webhook-secret          # Webhook HMAC 密钥
└── attachment-secret       # 附件签名链接密钥
```

- `rdm init` 创建目录并迁移到 head；`rdm serve` 启动时也会自动迁移。
- `rdm db status` / `db upgrade` / `db downgrade` 管理迁移版本。
- 迁移历史中 **0007 只接受空库重建**，升级前请先备份，详见 [runbook.md](runbook.md)。
- `webhook-secret`、`attachment-secret` 属于敏感数据；备份与权限按密钥处理。

## 日志与诊断

- 服务日志走 stdout/stderr，生产由 systemd/journald 或容器日志收集。
- 请求带请求上下文中间件；Webhook 投递状态可在 Web 中查看，`rdm doctor` 报告积压与失败。
- `rdm doctor --json` 便于接入监控；任一检查 FAIL 时退出码为 1。
