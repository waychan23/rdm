# rd-manager（rdm）

human/agent 协作的研发工作管理：受工作流引擎约束的 WorkItem/Sprint、站内信箱、
附件/产出物/工作区、Webhook 通知、27 个 MCP 工具与完整 Web。纯单人部署，SQLite，
服务只监听 127.0.0.1。

## 5 分钟跑起来

前置：Python 3.13 + [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                       # 安装依赖
uv run rdm init               # 初始化 ~/rdm-data 并迁移数据库
uv run rdm serve              # http://127.0.0.1:8765 （Ctrl-C 停止）
```

首次启动会创建默认项目 `RDM`、owner 成员、一次性 PAT 与初始登录密码，明文写到
`~/rdm-data/bootstrap-token` 和 `~/rdm-data/bootstrap-password`（文件权限均 0600）。

- Web：浏览器打开 <http://127.0.0.1:8765/>，用 owner + `bootstrap-password`
  登录（会话 cookie，7 天）：概览、看板拖拽、Backlog、Sprint、信箱、工作区、
  成员/Token 管理、工作项流转/附件/评论
- API 文档（FastAPI Swagger）：<http://127.0.0.1:8765/docs>
  （Bearer token 或登录会话）
- MCP endpoint：`http://127.0.0.1:8765/mcp`（原生 OAuth 2.1 或 Bearer PAT，见下）
- 自检：`uv run rdm doctor`（数据目录/迁移/bootstrap 凭据/workflow/端点/OAuth
  metadata/outbox 积压/附件孤儿，`--json`）
- 离线逃生（停服执行）：`rdm account reset-password`、`rdm bootstrap-token`

## 接入 agent CLI

```bash
uv run rdm integrate mcp           # 默认 OAuth：客户端首次连接时浏览器登录并选身份
uv run rdm integrate mcp --method token   # 旧方式：写死 Bearer PAT（CI/无浏览器环境）
uv run rdm skills install --target claude      # 安装 rdm-workflow skill
uv run rdm skills install --target opencode
```

### 目录级绑定：一个代码库目录 = 一个 member

典型场景：同一个 rdm 项目下，前端库由 frontend agent 负责、后端库由 backend agent
负责。在各自代码库目录里绑定对应 member，agent 在该目录启动时自动以该身份、
该项目工作（`whoami` 同时给出 member 与 project），skill/MCP 调用都不用显式指定：

```bash
cd ~/repo/demo-frontend
rdm integrate mcp --scope project --member frontend --project DEMO

cd ~/repo/demo-backend
rdm integrate mcp --scope project --member backend --project DEMO
```

- **身份与 CLI 解耦**：member 不属于任何特定 agent CLI。默认同时给 claude
  （`~/.claude.json` 按绝对路径键控，**token 不进代码库**）与 opencode
  （`<目录>/.opencode/opencode.json`，自动追加进该库 `.gitignore`）写入**同一个
  member token**——同一代码库目录下在 claude / opencode 间切换，身份与默认项目不变，
  `whoami` 始终一致；一个 member 也可签发多个 token。codex 无项目级配置，用
  `--scope user`。仅当需要「同目录不同 CLI 扮演不同成员」时才分别用
  `--target claude --member A` / `--target opencode --member B`。
- 需要 owner 凭据：环境变量 `RDM_TOKEN`（或 `--data-dir` 指向 bootstrap token）；
  命令会为该 member 签发一个专用 token（label 为 `project:<目录名>`）。
- 不想签发可直接 `--member-token <token>`；已有绑定变化需 `--force` 轮换。

输出会给出：

```bash
export RDM_TOKEN=$(cat ~/rdm-data/bootstrap-token)
export NO_PROXY=127.0.0.1,localhost   # 系统代理开启时必需
```

改完 agent 配置后重启对应 CLI。codex 的配置路径为推断值（未实测），输出会标注。

## 常用命令

```bash
uv run rdm project create DEMO --name "演示项目"
uv run rdm member create frontend --project DEMO --roles worker
uv run rdm member create backend  --project DEMO --roles worker
uv run rdm token issue <member-id>          # 给某成员签发 token
uv run rdm db status                        # 迁移版本
uv run rdm doctor                           # 环境自检（FAIL 退出码 1）
```

## Webhook 通知

在成员上配置 `notify_webhook`（Web 设置页或创建成员时）与格式
（generic/dingtalk/feishu）：工作项指派/状态变更投 assignee、新评论投该工作项负责人、
信件逐收件人映射为 `mailbox.delivered`、Sprint 启停广播给全部配置成员。
HMAC-SHA256 签名头 `X-RDM-Signature`，进程密钥在 `~/rdm-data/webhook-secret`；
失败按 1m/5m/15m 退避，首发 + 3 重试后标记 failed，`rdm doctor` 可查积压。

## 端到端验收

S1–S10 场景脚本用真实 `claude -p` / `opencode run` 驱动（需本机登录相应 CLI）：

```bash
uv run python e2e/run_e2e.py --cli claude,opencode
```

详见 [e2e/README.md](e2e/README.md)。

## 开发

```bash
uv run pytest -q                             # 全部测试
uv run ruff check . && uv run ruff format --check .
uv run mypy src/rdm/domain src/rdm/application

# 当前前端：React 18 + Atlaskit/ADS（architecture §16.62）
pnpm -C web-next install --ignore-scripts
pnpm -C web-next dev        # Vite dev server（代理 /api、OAuth、/mcp 到 8765）
pnpm -C web-next build      # 产物到 src/rdm/resources/web-next-dist

# 旧前端（Vue 3 + Element Plus），已冻结，仅维护性构建
pnpm -C web install --ignore-scripts && pnpm -C web build
```

服务默认发新版，`rdm serve --web-ui legacy`（或 `RDM_WEB_UI=legacy`）切旧版。

打 wheel 前两套前端都要构建（`uv build` 的 force-include 要求两个 dist 都存在）：

```bash
pnpm -C web-next install --frozen-lockfile --ignore-scripts && pnpm -C web-next build
pnpm -C web install --frozen-lockfile --ignore-scripts && pnpm -C web build
uv build
```

前端写码规则见仓库根 `CLAUDE.md`；测试与关键裁决见 `docs/`（architecture.md §16）。
M1 手工验收脚本见 `docs/acceptance/m1-loop.md`。
