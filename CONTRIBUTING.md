# 贡献指南

感谢参与 rdm。本文说明开发环境、测试与提交要求。

## 环境要求

- Python **3.13** + [uv](https://docs.astral.sh/uv/)
- Node **22** + pnpm **12**（仅前端）
- 可选：Docker（PostgreSQL / ParadeDB 测试）

## 后端开发

```bash
uv sync
uv run rdm init                     # 初始化 ~/rdm-data
uv run rdm serve                    # 127.0.0.1:8765
```

改动后必须通过：

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/rdm/domain src/rdm/application
```

本机开着系统代理时，loopback 测试可能 502：

```bash
NO_PROXY=127.0.0.1,localhost,::1 uv run pytest -q
```

PostgreSQL 后端（需要 Docker）：

```bash
RDM_TEST_BACKEND=postgres uv run pytest -q
RDM_TEST_BACKEND=both uv run pytest -q
```

## 前端开发

前端只有 `web-next/`（React 18 + Vite + TypeScript + Atlaskit）。旧 Vue 前端已移除。

```bash
pnpm -C web-next install --ignore-scripts
pnpm -C web-next dev                # 5173，代理 /api、/.well-known、/mcp
pnpm -C web-next lint               # type-aware ESLint；no-deprecated 为 error
pnpm -C web-next build
pnpm -C web-next e2e                # Playwright（先装 chromium）
```

UI 规范（ADS 组件、token、导入路径、模式）见仓库根 `CLAUDE.md` 的摘要；
完整内部规范仅本地维护，不随仓库发布。

改动前端后必须跑 `pnpm -C web-next lint`，不要用 `eslint-disable` 绕过废弃 API 检查。

## 目录约定

```
src/rdm/           后端（domain → application → infrastructure → interfaces）
web-next/          唯一前端（独立构建，不进 wheel）
tests/             pytest
e2e/               真实 agent CLI 验收（非 CI 默认）
deploy/            nginx / systemd 样例
docs/              用户文档（内部过程文档不入库）
```

业务规则只进 `domain/` / `application/`；UoW 是唯一提交点；MCP 工具签名变更需在内部设计
裁决记录 §17 追加（本地维护，不随仓库发布）。

## 提交与 PR

- 提交信息用中文或英文的祈使句，说明「做了什么、为什么」。
- 一个 PR 聚焦一件事；包含行为变化的 PR 请补测试。
- 发布版本号在 `src/rdm/__init__.py`（`__version__`）与 `web-next/package.json` 两处保持一致；
  tag 使用 `v<version>`。

## 许可证

贡献即表示同意以 [Apache-2.0](LICENSE) 许可发布。
