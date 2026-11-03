# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- Docker 镜像与 Compose 部署（后端、Web/nginx、可选 ParadeDB），见 `docs/docker.md`。
- 企业内网/容器部署可绑定非回环地址；非回环绑定要求显式 `RDM_PUBLIC_BASE_URL`。

### Changed

- `rdm serve` 不再拒绝非回环绑定；默认仍为 `127.0.0.1`。`/api/v1/local/*`
  （Owner 恢复）继续仅接受本机回环请求。

## [0.1.0] - 2026-11-03

首个公开版本。

### Added

- 工作流引擎：工作项类型 / 状态 / 命名步骤 / 审批与任务式步骤 / gate / 子类型。
- WorkItem、Sprint、Release 的 REST + MCP 管理，35 个 MCP 工具。
- 站内信箱、评论 @ 通知、Webhook 投递（generic / dingtalk / feishu）。
- 组织 / 用户 / Agent / 项目成员身份模型；PAT 与原生 OAuth（Auth Code + PKCE）。
- React 18 + Atlaskit Web UI（`web-next/`），独立构建部署。
- SQLite 默认后端，可选 PostgreSQL 18 + ParadeDB 全文搜索。
- `rdm` CLI：init / serve / doctor / db / project / user / me / skills / integrate / uninstall。
- GitHub Release 资产：wheel、sdist、前端产物、部署样例与校验和。

[Unreleased]: https://github.com/waychan23/rdm/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/waychan23/rdm/releases/tag/v0.1.0
