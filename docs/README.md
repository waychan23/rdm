# 文档索引

## 使用者 / 运维

| 文档 | 内容 |
|---|---|
| [README](../README.md) | 项目介绍、5 分钟本地运行、常用命令 |
| [deployment.md](deployment.md) | 从 Release 产物部署：wheel 安装、systemd、nginx、绑定模式、升级回滚 |
| [docker.md](docker.md) | Docker 镜像构建与 Compose 部署（含 TLS、PostgreSQL、备份升级） |
| [configuration.md](configuration.md) | 环境变量总表、数据目录布局、迁移与诊断 |
| [mcp-clients.md](mcp-clients.md) | MCP 客户端接入：OAuth / PAT、目录绑定、skills、排障 |
| [runbook.md](runbook.md) | 日常运维：启停、备份恢复、升级、故障处理 |
| [architecture.md](architecture.md) | 面向使用者的架构概览：组件、分层、领域模型、部署拓扑 |
| [mcp-tools.md](mcp-tools.md) | 35 个 MCP 工具、响应信封与错误码 |
| [workflow-config.md](workflow-config.md) | workflow JSON5 配置手册（状态、步骤、gate、子类型） |

## 贡献者 / 维护者

| 文档 | 内容 |
|---|---|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 开发环境、测试、代码规范、PR 流程 |
| [SECURITY.md](../SECURITY.md) | 漏洞报告渠道与安全边界 |
| [e2e/README.md](../e2e/README.md) | 真实 agent CLI 的 S1–S10 验收 |
| [web-next/e2e/README.md](../web-next/e2e/README.md) | Web UI Playwright e2e |

## 发布物

GitHub Release 提供：

- `rdm-<version>-py3-none-any.whl` —— 后端 API/CLI（不含前端）
- `rdm-<version>.tar.gz` —— 后端源码分发包（仅 `src/rdm` + tests + README/LICENSE）
- `web-next-dist-<version>.tar.gz` —— 前端静态产物（解压到 nginx 根目录）
- `deploy-<version>.tar.gz` —— nginx / systemd 部署样例
- `SHA256SUMS` —— 校验和
