# rd-manager（rdm）

[![ci](https://github.com/waychan23/rdm/actions/workflows/ci.yml/badge.svg)](https://github.com/waychan23/rdm/actions/workflows/ci.yml)
[![release](https://github.com/waychan23/rdm/actions/workflows/release.yml/badge.svg)](https://github.com/waychan23/rdm/actions/workflows/release.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

human/agent 协作的研发工作管理，核心取向是**渐进式协作**：不改变团队熟悉的、以人为主的敏捷流程，
而是把 AI Agent 作为正式成员引入——有自己的账号、项目角色、待办与信箱，从承担单个任务开始，
逐步参与需求、开发、评审、测试与发布，自动化程度随流程成熟度逐步提高。

系统用工作流引擎约束协作边界：WorkItem/Sprint/版本发布、状态机与审批 gate、站内信箱与 @ 通知、
附件/产出物、Webhook、全局搜索，以及 35 个 MCP 工具和完整 Web。单组织自托管，默认 SQLite
（可选 PostgreSQL + ParadeDB 搜索）。服务默认只监听 127.0.0.1；企业内网/容器部署可绑定内网地址，
敏感恢复端点仍仅限本机。

## 安装与部署

- **生产部署**（从 Release 下载 wheel + 前端产物，systemd + nginx）：[docs/deployment.md](docs/deployment.md)
- **Docker 部署**（compose 构建后端 + Web + 可选 ParadeDB）：[docs/docker.md](docs/docker.md)
- **配置参考**（环境变量、数据目录、迁移）：[docs/configuration.md](docs/configuration.md)
- **MCP 客户端接入**（OAuth / PAT、目录级绑定、skills）：[docs/mcp-clients.md](docs/mcp-clients.md)
- **完整文档索引**：[docs/README.md](docs/README.md)

从源码开发请继续往下看。

## 源码开发：5 分钟跑起来

前置：Python 3.13 + [uv](https://docs.astral.sh/uv/)；Web 前端另需 Node 22 + pnpm。

```bash
uv sync                       # 安装后端依赖
uv run rdm init               # 初始化 ~/rdm-data 并迁移数据库
# 终端 A：API/MCP 服务（dev 时把 public origin 指向前端，便于登录/恢复链接）
RDM_PUBLIC_BASE_URL=http://127.0.0.1:5173 uv run rdm serve

# 终端 B：Web 前端（Vite dev server，HMR，无需 build）
pnpm -C web-next install --ignore-scripts
pnpm -C web-next dev          # http://127.0.0.1:5173
```

首次启动会创建默认组织与无密码的 Org Owner，在日志里打印**一次性 bootstrap-url**
（`RDM_PUBLIC_BASE_URL` 设置后指向 5173）：

```
首次启动：请在本机打开设置 Org Owner 密码：http://127.0.0.1:5173/set-password?ticket=...
（7 天内有效；丢失可执行 `rdm account recover-owner` 重新生成）
```

- Web：打开该 URL 设置密码，然后用浏览器访问 <http://127.0.0.1:5173/> 登录。
  登录是无状态 OAuth（Auth Code + PKCE），不再有会话 cookie；支持「记住我」
  （7 天滑动续期，绝对上限 30 天）。
- 首次登录没有默认项目；组织 Owner 或 `project-director` 在 Web 里创建项目。
- API 文档（FastAPI Swagger）：<http://127.0.0.1:8765/api/docs>（Bearer PAT/OAuth token）
- MCP endpoint：`http://127.0.0.1:8765/mcp`（原生 OAuth 2.1 或 Bearer PAT，见下）。
  生产设置 `RDM_PUBLIC_BASE_URL` 后 OAuth discovery 指向公网 origin；本地 agent 应改用
  `https://<public-origin>/mcp`，或继续用 PAT 直连 loopback。
- 自检：`uv run rdm doctor`（数据目录/迁移/Org Owner/workflow/端点/OAuth
  metadata/outbox 积压/附件孤儿，`--json`）
- Org Owner 忘记密码：在部署主机执行 `rdm account recover-owner --public-url http://127.0.0.1:5173`
  （需服务运行；通过仅回环的 HTTP 端点重新生成 bootstrap-url）

> Python 进程只提供 API/CLI，不托管 Web 静态资源。生产部署用
> nginx 托管 `web-next/dist` 并反代 `/api/`、`/mcp`、`/.well-known/`，样例见
> [deploy/nginx/rdm.conf](deploy/nginx/rdm.conf)。

## 可选：PostgreSQL + ParadeDB 后端

SQLite 仍是默认。需要共享数据库或更好的中文全文搜索时，可切换到 PostgreSQL：

```bash
uv sync --extra postgres
# 必须使用带 pg_search 扩展的镜像（ParadeDB 官方 PG 18 镜像）
docker run -d --name rdm-pg \
  -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=rdm \
  -p 5432:5432 paradedb/paradedb:0.26.4-pg18

export RDM_DATABASE_URL=postgresql://postgres:change-me@127.0.0.1:5432/rdm
uv run rdm init
uv run rdm serve
```

- `RDM_DATABASE_URL`（或 `--database-url`）同时作用于 `init|serve|db|doctor|workflow validate`；
  原生 PostgreSQL 没有 `pg_search` 时 `rdm init/serve` 会直接报错。
- `data-dir` 仍然保存 `projects/`、`webhook-secret`、`attachment-secret`（数据库不再放在这里）。
- 搜索：SQLite 用 FTS5 trigram；PostgreSQL 用 ParadeDB BM25 + jieba 分词，
  1–2 字符的短查询回退 `ILIKE`。
- 备份改用 `pg_dump`，见 [docs/runbook.md](docs/runbook.md)。
- 测试：`RDM_TEST_BACKEND=postgres|both uv run pytest -q`（testcontainers 复用
  `paradedb/paradedb:0.26.4-pg18`，每个测试独立 database）。

## 身份模型（组织/用户/项目）

- **组织**：单组织，初始化自动创建；不可新建组织（代码按 `org_id` 隔离，便于扩展）。
- **用户**：`human` 或 `agent`，归属组织，由组织管理。`agent` 必须有一个 human manager。
- **项目**：归属组织；创建者自动成为 Project Owner；项目成员是「项目↔用户」关系。
- **组织角色**：`org_owner`（唯一、可转让）、`user_manager`（用户管理）、
  `project_director`（建项目、改派项目经理）。
- **项目角色**：`project_owner / manager / sprint_manager / worker`。
- **Agent 管理**：由 manager 本人在「我的设置 → Agent 账号」创建/停用；human 加入
  项目时其启用 agent 自动成为项目成员。停用 human 会级联撤销其 agent 的访问权。

## 接入 agent CLI

```bash
uv run rdm integrate mcp           # 默认 OAuth：客户端首次连接时浏览器登录并选身份
uv run rdm integrate mcp --method token   # 静态 Bearer PAT（CI/无浏览器环境）
uv run rdm skills install --target claude      # 安装 rdm-workflow skill
uv run rdm skills install --target opencode
```

生产环境用 `--url https://<public-origin>/mcp`；通用客户端配置、OAuth 排障与卸载见
[docs/mcp-clients.md](docs/mcp-clients.md)。仓库根 `.mcp.json.example` 是本地开发用的客户端配置模板
（真实文件 `.mcp.json` 不入库）。

PAT 只能由本人在 Web「我的设置 → 访问令牌」或 `rdm me token-create` 创建；管理员
不能代签，只能批量撤销。令牌可指定「使用身份」为本人或自己管理的某个 agent。

### 目录级绑定：一个代码库目录 = 一个身份

典型场景：同一个 rdm 项目下，前端库由 frontend agent 负责、后端库由 backend agent
负责。先用**对应身份的 PAT** 绑定目录（无浏览器环境），agent 在该目录启动时自动以
该身份工作（`whoami` 同时给出身份与项目）：

```bash
cd ~/repo/demo-frontend
rdm integrate mcp --scope project --method token --member-token "$FRONTEND_PAT"

cd ~/repo/demo-backend
rdm integrate mcp --scope project --method token --member-token "$BACKEND_PAT"
```

- **身份与 CLI 解耦**：identity 不属于任何特定 agent CLI。默认同时给 claude
  （`~/.claude.json` 按绝对路径键控，**token 不进代码库**）与 opencode
  （`<目录>/.opencode/opencode.json`，自动追加进该库 `.gitignore`）写入**同一个
  token**——同一目录下在 claude / opencode 间切换，身份与默认项目不变。
  codex 无项目级配置，用 `--scope user`。
- `--method oauth` 的项目级绑定不写 secret，首次使用在浏览器同意页选择本人或自己的 agent。
- 已有绑定变化需 `--force` 轮换。

## 常用命令

```bash
uv run rdm project create DEMO --name "演示项目"
uv run rdm user create alice                 # 打印一次性设置密码链接（24h）
uv run rdm project members add --user alice --roles worker --project DEMO
uv run rdm me token-create --label cli --as-agent my-agent   # 自助 PAT（可选 act-as）
uv run rdm user disable alice
uv run rdm user roles alice --roles project-director          # 仅 Org Owner
uv run rdm org transfer-owner bob                             # 转让 Org Owner
uv run rdm db status                        # 迁移版本
uv run rdm doctor                           # 环境自检（FAIL 退出码 1）
```

## Webhook 通知

在「我的设置」（human）或 agent 资料里配置 `notify_webhook` 与格式
（generic/dingtalk/feishu）：工作项指派/状态变更投 assignee、新评论投该工作项负责人、
信件逐收件人映射为 `mailbox.delivered`、Sprint 启停与版本发布广播给全部配置成员（停用的 human
及其 agent 不投递）。
HMAC-SHA256 签名头 `X-RDM-Signature`，进程密钥在 `~/rdm-data/webhook-secret`；
失败按 1m/5m/15m 退避，首发 + 3 重试后标记 failed，`rdm doctor` 可查积压。

## 端到端验收

S1–S10 场景脚本用真实 `claude -p` / `opencode run` 驱动（需本机登录相应 CLI）：

```bash
uv run python e2e/run_e2e.py --cli claude,opencode
```

详见 [e2e/README.md](e2e/README.md)。

Web UI 的浏览器 e2e（重点覆盖工作流引擎的命名步骤、审批、gate/retry、
任务式子任务、子类型与看板拖拽规则）使用 Playwright 驱动构建后的 SPA：

```bash
pnpm -C web-next e2e
```

详见 [web-next/e2e/README.md](web-next/e2e/README.md)。

## 开发

```bash
uv run pytest -q                             # 全部测试
uv run ruff check . && uv run ruff format --check .
uv run mypy src/rdm/domain src/rdm/application

# 前端：React 18 + Atlaskit/ADS（唯一前端）
pnpm -C web-next install --ignore-scripts
pnpm -C web-next dev        # Vite dev server（代理 /api、/.well-known、/mcp 到 8765，HMR）
pnpm -C web-next lint       # ESLint（type-aware；@typescript-eslint/no-deprecated 为 error）
pnpm -C web-next build      # 产物到 web-next/dist（不随 wheel 发布）
```

后端 wheel 只含 API/CLI；打 wheel 前不再需要构建前端：

```bash
uv build
```

前端产物单独部署给 nginx/ingress（样例 `deploy/nginx/rdm.conf`）。

前端写码规则见仓库根 `CLAUDE.md`（含 UI 设计与组件/token 规范摘要）；
工作流配置 `workflow-configs/*.json5` 的完整手册见 [docs/workflow-config.md](docs/workflow-config.md)；
（首次启动会把包内默认定义复制到 `<data-dir>/workflow-configs/`，修改后重启生效；项目创建时必选一份启用中的配置版本。）
运维/备份/升级/排障见 [docs/runbook.md](docs/runbook.md)；
测试要求见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [e2e/README.md](e2e/README.md)。

## 参与贡献

开发环境、测试与提交要求见 [CONTRIBUTING.md](CONTRIBUTING.md)；安全问题请按
[SECURITY.md](SECURITY.md) 私下报告。

## 许可证

[Apache License 2.0](LICENSE)，版权声明见 [NOTICE](NOTICE)。
