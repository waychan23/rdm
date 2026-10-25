# rd-manager（rdm）

human/agent 协作的研发工作管理：受工作流引擎约束的 WorkItem/Sprint、站内信箱、
MCP 工具与最小 Web。纯单人部署，SQLite，服务只监听 127.0.0.1。

## 5 分钟跑起来

前置：Python 3.13 + [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                       # 安装依赖
uv run rdm init               # 初始化 ~/rdm-data 并迁移数据库
uv run rdm serve              # http://127.0.0.1:8765 （Ctrl-C 停止）
```

首次启动会创建默认项目 `RDM`、owner 成员与一次性 token，明文写到
`~/rdm-data/bootstrap-token`（文件权限 0600），并在控制台提示。

- Web：浏览器打开 <http://127.0.0.1:8765/>（回环无 token 时以 owner 身份访问）
- API 文档（FastAPI Swagger）：<http://127.0.0.1:8765/docs>
- MCP endpoint：`http://127.0.0.1:8765/mcp`（Bearer token，见下）

## 接入 agent CLI

```bash
uv run rdm integrate mcp           # 生成 claude/codex/opencode 三家 user 级配置
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

- 默认同时写 claude（`~/.claude.json` 按绝对路径键控，**token 不进代码库**）
  与 opencode（`<目录>/.opencode/opencode.json`，自动追加进该库 `.gitignore`）；
  `--target` 可只选一家；codex 无项目级配置，不支持。
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
```

## 开发

```bash
uv run pytest -q                             # 全部测试
uv run ruff check . && uv run ruff format --check .
uv run mypy src/rdm/domain src/rdm/application

cd web && pnpm install --ignore-scripts && pnpm build   # 构建 Web 到包资源目录
cd web && pnpm dev                                       # Vite dev server（代理 /api、/mcp）
```

打 wheel 前先构建 Web（`uv build` 的 force-include 要求 web-dist 存在）：

```bash
(cd web && pnpm install --frozen-lockfile --ignore-scripts && pnpm build)
uv build
```

测试与关键裁决见 `docs/`（四份设计文档 + architecture.md §16）。
M1 手工验收脚本见 `docs/acceptance/m1-loop.md`。
