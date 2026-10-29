# rd-manager（rdm）

human/agent 协作的研发工作管理：受工作流引擎约束的 WorkItem/Sprint、站内信箱、
附件/产出物/工作区、Webhook 通知、27 个 MCP 工具与完整 Web。单组织部署（初始化
创建默认组织，预留多租户隔离），SQLite，服务只监听 127.0.0.1。

## 5 分钟跑起来

前置：Python 3.13 + [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                       # 安装依赖
uv run rdm init               # 初始化 ~/rdm-data 并迁移数据库
uv run rdm serve              # http://127.0.0.1:8765 （Ctrl-C 停止）
```

首次启动会创建默认组织与无密码的 Org Owner，在日志里打印**一次性 bootstrap-url**：

```
首次启动：请在本机打开设置 Org Owner 密码：http://127.0.0.1:8765/set-password?ticket=...
（7 天内有效；丢失可执行 `rdm account recover-owner` 重新生成）
```

- Web：打开该 URL 设置密码，然后用浏览器访问 <http://127.0.0.1:8765/> 登录。
  登录是无状态 OAuth（Auth Code + PKCE），不再有会话 cookie；支持「记住我」
  （7 天滑动续期，绝对上限 30 天）。
- 首次登录没有默认项目；组织 Owner 或 `project-director` 在 Web 里创建项目。
- API 文档（FastAPI Swagger）：<http://127.0.0.1:8765/docs>（Bearer PAT/OAuth token）
- MCP endpoint：`http://127.0.0.1:8765/mcp`（原生 OAuth 2.1 或 Bearer PAT，见下）
- 自检：`uv run rdm doctor`（数据目录/迁移/Org Owner/workflow/端点/OAuth
  metadata/outbox 积压/附件孤儿，`--json`）
- Org Owner 忘记密码：在部署主机执行 `rdm account recover-owner`（需服务运行；
  通过仅回环的 HTTP 端点重新生成 bootstrap-url）

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
信件逐收件人映射为 `mailbox.delivered`、Sprint 启停广播给全部配置成员（停用的 human
及其 agent 不投递）。
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

# 前端：React 18 + Atlaskit/ADS（唯一前端，architecture §17.72）
pnpm -C web-next install --ignore-scripts
pnpm -C web-next dev        # Vite dev server（代理 /api、OAuth、/mcp 到 8765）
pnpm -C web-next build      # 产物到 src/rdm/resources/web-next-dist
```

打 wheel 前先构建前端：

```bash
pnpm -C web-next install --frozen-lockfile --ignore-scripts && pnpm -C web-next build
uv build
```

前端写码规则见仓库根 `CLAUDE.md`，UI 设计与组件/token 规范见 [docs/web-next-ui.md](docs/web-next-ui.md)；
测试与关键裁决见 `docs/`（architecture.md §16/§17）。
M1 手工验收脚本见 `docs/acceptance/m1-loop.md`。
