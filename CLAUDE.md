# rd-manager（rdm）协作约定

human/agent 协同研发管理工具：Python/FastAPI/FastMCP 单体，两个组成部分：

- `src/rdm/`：后端（domain → application → infrastructure → interfaces 分层）。
- `web-next/`：**唯一前端**，React 18 + Vite + TypeScript + Atlassian Design System（Atlaskit）。
  旧 Vue 版 `web/` 已在 M5 删除（架构 §17.72）。

## 身份模型（M5 起）

- `organization`（单组织）→ `users`（human/agent）→ `project` ← `project_member`（关系）。
  项目角色只挂在 human 的关系行；agent 随其 manager 自动入项，不能单独增删。
- 组织角色：`org_owner`（唯一）、`user_manager`、`project_director`。
- Web 认证是**无状态 OAuth**（first-party `rdm-web`，Auth Code + PKCE，Bearer token），
  没有 cookie session；CLI 用 PAT；MCP 同时支持 OAuth 与 PAT。
- PAT 只能本人创建，可 `act_as` 自己管理的 agent；用户管理角色只能撤销、不能代签。

## 前端需求归属

- 所有新需求、新页面、交互改动、UI/前端缺陷，只在 `web-next/` 实现。
- 前后端共享 REST/MCP 契约（MCP 工具新增/签名变更须在内部设计裁决记录 §17 登记，当前 36 个；该记录仅本地维护、不随仓库发布）。

## 常用命令

- 后端：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src/rdm/domain src/rdm/application`。
  本机开着系统代理时，loopback 测试会 502，加 `NO_PROXY=127.0.0.1,localhost,::1`。
- PostgreSQL 后端（可选，§17.114）：`RDM_TEST_BACKEND=postgres|both uv run pytest -q`
  （testcontainers 用 `paradedb/paradedb:0.26.4-pg18`，每测试独立库；Docker 不可用时跳过）。
  手工冒烟：`uv sync --extra postgres`，起 ParadeDB 镜像，
  `RDM_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:5432/rdm uv run rdm init|serve|doctor`。
- 前端：`pnpm -C web-next dev`（5173，代理 `/api`、`/.well-known`、`/mcp` 到 8765，HMR）、
  `pnpm -C web-next lint`（deprecated API 门禁）、
  `pnpm -C web-next build`（产物进 `web-next/dist`，独立部署给 nginx，不进 wheel）。
  开发时后端加 `RDM_PUBLIC_BASE_URL=http://127.0.0.1:5173`，登录/恢复链接才指向 dev server。
  前端 e2e（Playwright，重点覆盖工作流引擎）：`pnpm -C web-next e2e`（先 build，再以 `vite preview`
  起生产产物 + 代理；首次需 `pnpm -C web-next exec playwright install chromium`）。详见 `web-next/e2e/README.md`。
- 起服务：`uv run rdm serve`（纯 API/MCP/OAuth，不托管 Web）；首次启动看日志里的 **bootstrap-url**
  设置 Org Owner 密码。Owner 找回：`uv run rdm account recover-owner --public-url http://127.0.0.1:5173`
  （需服务在本机运行）。
- root 路径只有三类：`/api/*`（REST、`/api/oauth/*`、`/api/healthz`、`/api/docs`）、`/mcp`、
  `/.well-known/*`。生产用 nginx 托管 `web-next/dist` 并反代这三类路径（样例 `deploy/nginx/rdm.conf`）。
- wheel 只含 API/CLI，打包前不需要构建前端；前端产物单独部署。
- npm 下载挂起时走本地代理：`HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890`。

## 写 web-next/ 下的 UI 时

完整内部规范见本地 `docs/internal/web-next-ui.md`（已 gitignore，不随仓库发布；ADS 工具用法、token 规则与短名坑、
组件导入路径、状态/类型配色、表格/对话框/覆盖面板模式、新页面 checklist）——动手前先读。

- 动手前先用 ads-mcp（`.mcp.json`，由 `.mcp.json.example` 复制，工具名 `mcp__ads-mcp__*`）或
  `npx @atlaskit/ads-cli search/docs ... [--json]` 确认组件名、token 名、用法；查不到再用 `atlaskit_*` fallback 工具。
- 颜色、间距、圆角、阴影、字体、层级一律走 `@atlaskit/tokens`（`token('…')` / CSS 变量 `var(--ds-…)`），
  不写裸 hex/rgb、不手造间距值；无法避免的例外（markdown 排版等）在同行注释说明。
- 优先用 `@atlaskit/*` 组件；自定义布局用 `@atlaskit/primitives/compiled` + `@atlaskit/css` 的 `cssMap`（Compiled 插件已接入，见 `web-next/vite.config.ts`）。
- 中文排版只允许在 `src/styles/global.css` 的字体栈**追加** CJK fallback（PingFang/YaHei/Noto），不引字体包、不改 token 值。
- 深色模式不做（固定 light）；a11y 工具开发时可用，但本期没有 UI 走查/lint/截图门禁，不要自行新建。
- 认证：所有 `/api/v1` 请求由 `lib/api.ts` 注入 Bearer 并在 401 时单飞刷新；不要在页面里手写 token。
  登录/OAuth 流程见 `lib/oauth.ts`（PKCE、localStorage token、`beginLogin`）。
- **改完前端必须跑 `pnpm -C web-next lint`**（type-aware ESLint，`@typescript-eslint/no-deprecated` 为 error）。
  ADS 的废弃 API 以组件 JSDoc 的 `@deprecated` 为准，按提示的替代方案改，不要使用已废弃 prop
  （例如 `ModalDialog` 的 `shouldCloseOnEscapePress` 已废弃，应在 `onClose` 里按条件拦截）。
  不要用 `eslint-disable` 绕过；如果确实无法避免，先和用户确认。

## 后端铁律

业务规则只进 domain/application；MCP 工具变更须在 §17 记裁决（当前 36 个）；UoW 唯一提交点；默认仅回环绑定（企业部署可显式绑定内网地址，敏感本地端点仍仅限本机）；
PAT 是永久自动化路径。细节与历史裁决见本地 `docs/internal/architecture.md` §16/§17（不随仓库发布；冲突以编号靠后的裁决为准）。
