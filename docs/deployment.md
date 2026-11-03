# 部署指南

本文面向自托管部署者：从 GitHub Release 产物安装 rdm，用 systemd 跑后端、nginx 托管前端。
本地源码开发见仓库根 [README](../README.md)。

## 组件与拓扑

```
浏览器 ──HTTPS──> nginx ──/api/、/mcp、/.well-known/──> rdm serve（默认 127.0.0.1:8765）
                     └── 静态文件：web-next/dist
```

- Python 进程只提供 API/CLI/MCP，**不托管 Web 静态资源**。
- 服务默认绑定回环地址；企业内网/容器/跨主机部署可显式绑定内网地址（见下）。
- 容器化部署见 [docker.md](docker.md)。

## 绑定地址与访问边界

| 场景 | 命令 | 说明 |
|---|---|---|
| nginx 与 rdm 同机（默认，推荐） | `rdm serve --host 127.0.0.1` | 只有本机 nginx 能访问 |
| 容器 / 跨主机内网 | `RDM_PUBLIC_BASE_URL=https://rdm.example.com rdm serve --host 0.0.0.0` | 端口只对反向代理/内网开放 |

- **非回环绑定必须设置 `RDM_PUBLIC_BASE_URL`**（用户与 MCP 客户端访问的 HTTPS origin），
  否则 CLI 拒绝启动——OAuth discovery、`web_url`、附件链接都依赖它。
- 非回环绑定时，用防火墙/安全组只允许反向代理来源访问 8765；不要把该端口直接暴露到公网。
- `/api/v1/local/*`（Org Owner 恢复等敏感操作）**始终只接受本机回环请求**，并且拒绝带
  `X-Forwarded-For` / `X-Real-IP` 的代理请求；nginx 样例也会直接返回 404。
  因此恢复命令必须在部署主机（或后端容器）内执行。
- OAuth 要求公网 origin 使用 HTTPS；内网可用企业 CA 签发证书。

## 1. 准备主机

- Python **3.13**
- 安装 [uv](https://docs.astral.sh/uv/)
- nginx（或同等反向代理）
- 可选：PostgreSQL 18 + ParadeDB 镜像（需要全文搜索时）

```bash
sudo useradd --system --home /var/lib/rdm --shell /usr/sbin/nologin rdm
sudo mkdir -p /var/lib/rdm /etc/rdm /var/www/rdm
sudo chown -R rdm:rdm /var/lib/rdm
```

## 2. 安装后端

从 Release 页面下载 `rdm-<version>-py3-none-any.whl`（以及 `SHA256SUMS` 校验）：

```bash
sha256sum -c SHA256SUMS --ignore-missing
sudo -u rdm uv tool install /path/to/rdm-0.1.0-py3-none-any.whl
```

需要 PostgreSQL 后端时：

```bash
sudo -u rdm uv tool install "rdm[postgres] @ /path/to/rdm-0.1.0-py3-none-any.whl"
```

初始化数据目录与数据库：

```bash
sudo -u rdm rdm init --data-dir /var/lib/rdm
```

## 3. 配置 systemd

```bash
sudo cp deploy/systemd/rdm.service /etc/systemd/system/
sudo cp deploy/systemd/rdm.env.example /etc/rdm/rdm.env
sudo editor /etc/rdm/rdm.env       # 至少改 RDM_PUBLIC_BASE_URL
sudo systemctl daemon-reload
sudo systemctl enable --now rdm
```

> nginx 在另一台主机时，把 `/etc/rdm/rdm.env` 的 `RDM_HOST` 改为 `0.0.0.0`（或具体内网 IP），
> 同时设置 `RDM_PUBLIC_BASE_URL`，并用防火墙只放行 nginx 来源访问 8765。

检查启动日志里的**一次性 bootstrap-url**：

```bash
sudo journalctl -u rdm -n 50
```

在浏览器打开该 URL 设置 Org Owner 密码（7 天内有效；丢失可执行
`rdm account recover-owner --public-url https://<你的域名>`）。

`rdm doctor` 可检查数据目录、迁移版本、Org Owner、workflow、端点、OAuth metadata、
outbox 积压与附件孤儿：

```bash
sudo -u rdm rdm doctor --data-dir /var/lib/rdm
```

## 4. 部署前端

```bash
tar -xzf web-next-dist-<version>.tar.gz -C /var/www/rdm
```

nginx 样例见 [deploy/nginx/rdm.conf](../deploy/nginx/rdm.conf)，按实际域名与证书路径修改后：

```bash
sudo cp deploy/nginx/rdm.conf /etc/nginx/conf.d/rdm.conf
sudo nginx -t && sudo systemctl reload nginx
```

要点：

- `RDM_PUBLIC_BASE_URL` 必须是用户与 MCP 客户端访问的 **公网 origin**（非回环时必须 HTTPS）。
- nginx 只反代 `/api/`、`/mcp`、`/.well-known/` 三类路径；`/api/v1/local/` 必须封禁（样例已包含）。
- SPA 使用 history fallback（`try_files ... /index.html`）。

## 5. 升级与回滚

```bash
sudo systemctl stop rdm
sudo -u rdm uv tool install --reinstall /path/to/rdm-<new>.whl
sudo -u rdm rdm db upgrade --data-dir /var/lib/rdm
sudo systemctl start rdm
```

- `rdm serve` 启动时也会自动执行迁移；`rdm db status` 查看当前 revision。
- 备份、恢复、迁移注意事项见 [runbook.md](runbook.md)。
- 回滚需同时回退 wheel 与数据库（先恢复备份再降级版本）。

## 6. PostgreSQL / ParadeDB（可选）

```bash
docker run -d --name rdm-pg \
  -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=rdm \
  -p 5432:5432 paradedb/paradedb:0.26.4-pg18
```

在 `/etc/rdm/rdm.env` 设置：

```ini
RDM_DATABASE_URL=postgresql://postgres:change-me@127.0.0.1:5432/rdm
```

然后 `rdm init` / 重启服务。原生 PostgreSQL 缺少 `pg_search` 扩展时启动会直接报错。

## 7. 安全边界

- 默认只监听回环；绑定内网地址时，用防火墙/安全组限制来源，并确保前方有 TLS 反向代理。
  不要把 8765 直接暴露到公网。
- `/api/v1/local/*` 始终只接受本机回环请求（Owner 恢复请在部署主机或后端容器内执行）。
- 使用 HTTPS；OAuth issuer 在非回环场景必须是 HTTPS。
- 限制 `/api/docs`、`/api/openapi.json` 的访问（样例 nginx 可按需加 IP 白名单）。
- PAT 只由本人在 Web/CLI 创建；泄露后在「我的设置 → 访问令牌」撤销。
- 数据目录包含 SQLite 数据库与 HMAC 密钥（`webhook-secret`、`attachment-secret`），按敏感数据处理。
