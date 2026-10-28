# rd-manager（rdm）协作约定

human/agent 协同研发管理工具：Python/FastAPI/FastMCP 单体，三个组成部分：

- `src/rdm/`：后端（domain → application → infrastructure → interfaces 分层）。
- `web-next/`：**当前前端**，React 18 + Vite + TypeScript + Atlassian Design System（Atlaskit）。
- `web/`：旧 Vue 3 + Element Plus 前端，**已冻结，不要往里加功能或改样式**（架构 §16.62）。

## 常用命令

- 后端：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src/rdm/domain src/rdm/application`。
  本机开着系统代理时，loopback 测试会 502，加 `NO_PROXY=127.0.0.1,localhost,::1`。
- 前端：`pnpm -C web-next dev`（5173，代理 API 到 8765）、`pnpm -C web-next build`（产物进 `src/rdm/resources/web-next-dist`）。
- 起服务：`uv run rdm serve`；`--web-ui next|legacy`（或 `RDM_WEB_UI`）切换发哪套前端，默认 next。
- wheel 打包前两套前端都要 build：`pnpm -C web-next build && pnpm -C web build`。
- npm 下载挂起时走本地代理：`HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890`。

## 写 web-next/ 下的 UI 时

- 动手前先用 ads-mcp（`.mcp.json` 已配，工具名 `mcp__ads-mcp__*`）或
  `npx @atlaskit/ads-cli search/docs ... [--json]` 确认组件名、token 名、用法；查不到再用 `atlaskit_*` fallback 工具。
- 颜色、间距、圆角、阴影、字体、层级一律走 `@atlaskit/tokens`（`token('…')` / CSS 变量 `var(--ds-…)`），
  不写裸 hex/rgb、不手造间距值；无法避免的例外（markdown 排版等）在同行注释说明。
- 优先用 `@atlaskit/*` 组件；自定义布局用 `@atlaskit/primitives` + `@atlaskit/css`（xcss）。
- 中文排版只允许在 `src/styles/global.css` 的字体栈**追加** CJK fallback（PingFang/YaHei/Noto），不引字体包、不改 token 值。
- 深色模式不做（固定 light）；a11y 工具（`ads_analyze_a11y`/`ads_analyze_localhost_a11y`）开发时可用，但本期没有 UI 走查/lint/截图门禁，不要自行新建。
- 功能范围与旧 Vue 版 1:1，不趁重写补新功能；缺口记 backlog（见 docs/HANDOFF-M3.md §6）。

## 后端铁律

业务规则只进 domain/application；MCP 27 工具锁死；UoW 唯一提交点；仅回环绑定；
PAT 是永久自动化路径。细节与历史裁决见 `docs/architecture.md` §16（冲突以编号靠后的裁决为准）。
