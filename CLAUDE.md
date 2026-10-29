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
- 前后端共享 REST/MCP 契约（MCP 工具新增/签名变更须在 `docs/architecture.md` §17 记裁决，当前 28 个）。

## 常用命令

- 后端：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src/rdm/domain src/rdm/application`。
  本机开着系统代理时，loopback 测试会 502，加 `NO_PROXY=127.0.0.1,localhost,::1`。
- 前端：`pnpm -C web-next dev`（5173，代理 API 到 8765）、`pnpm -C web-next build`（产物进 `src/rdm/resources/web-next-dist`）。
- 起服务：`uv run rdm serve`；首次启动看日志里的 **bootstrap-url** 设置 Org Owner 密码。
  Owner 找回：`uv run rdm account recover-owner`（需服务在本机运行）。
- wheel 打包前 build 前端：`pnpm -C web-next build`。
- npm 下载挂起时走本地代理：`HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890`。

## 写 web-next/ 下的 UI 时

完整规范见 **[docs/web-next-ui.md](docs/web-next-ui.md)**（ADS 工具用法、token 规则与短名坑、
组件导入路径、状态/类型配色、表格/对话框/覆盖面板模式、新页面 checklist）——动手前先读。

- 动手前先用 ads-mcp（`.mcp.json` 已配，工具名 `mcp__ads-mcp__*`）或
  `npx @atlaskit/ads-cli search/docs ... [--json]` 确认组件名、token 名、用法；查不到再用 `atlaskit_*` fallback 工具。
- 颜色、间距、圆角、阴影、字体、层级一律走 `@atlaskit/tokens`（`token('…')` / CSS 变量 `var(--ds-…)`），
  不写裸 hex/rgb、不手造间距值；无法避免的例外（markdown 排版等）在同行注释说明。
- 优先用 `@atlaskit/*` 组件；自定义布局用 `@atlaskit/primitives/compiled` + `@atlaskit/css` 的 `cssMap`（Compiled 插件已接入，见 `web-next/vite.config.ts`）。
- 中文排版只允许在 `src/styles/global.css` 的字体栈**追加** CJK fallback（PingFang/YaHei/Noto），不引字体包、不改 token 值。
- 深色模式不做（固定 light）；a11y 工具开发时可用，但本期没有 UI 走查/lint/截图门禁，不要自行新建。
- 认证：所有 `/api/v1` 请求由 `lib/api.ts` 注入 Bearer 并在 401 时单飞刷新；不要在页面里手写 token。
  登录/OAuth 流程见 `lib/oauth.ts`（PKCE、localStorage token、`beginLogin`）。

## 后端铁律

业务规则只进 domain/application；MCP 工具变更须在 §17 记裁决（当前 28 个）；UoW 唯一提交点；仅回环绑定；
PAT 是永久自动化路径。细节与历史裁决见 `docs/architecture.md` §16/§17（冲突以编号靠后的裁决为准）。
