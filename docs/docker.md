# Docker 构建与部署

仓库提供两个镜像定义与一份 Compose 编排：

| 文件 | 作用 |
|---|---|
| [deploy/docker/backend.Dockerfile](../deploy/docker/backend.Dockerfile) | Python 3.13 + `rdm serve`（API/CLI/MCP，含 PostgreSQL 驱动） |
| [deploy/docker/web.Dockerfile](../deploy/docker/web.Dockerfile) | Node 22 构建 `web-next/dist`，由 nginx 托管并反代后端 |
| [deploy/docker/nginx.conf](../deploy/docker/nginx.conf) | 容器内 nginx：SPA + `/api/`、`/mcp`、`/.well-known/` |
| [docker-compose.yml](../docker-compose.yml) | `rdm` + `web`（+ 可选 `db` ParadeDB） |

## 前置条件

- Docker 24+ 与 Compose v2
- 一个用户可访问的 **HTTPS origin**（如 `https://rdm.example.com`），由企业负载均衡、
  ingress 或宿主机 nginx 终止 TLS 后转发到 `web` 容器的 `8080`

> 后端容器内使用 `rdm serve --host 0.0.0.0`。这是企业部署的正常形态；`/api/v1/local/*`
> （Owner 恢复）仍然只接受容器内的回环请求，不会随端口暴露。

## 快速启动

```bash
export RDM_PUBLIC_BASE_URL=https://rdm.example.com
docker compose up -d --build
docker compose ps
```

首次启动后，从后端日志取一次性 bootstrap-url：

```bash
docker compose logs rdm | grep -i bootstrap
```

把日志中的链接域名替换为你的公网 origin（若 `RDM_PUBLIC_BASE_URL` 已正确设置，链接本身就是
公网地址），在浏览器打开设置 Org Owner 密码。

## 配置

| 变量 | 说明 |
|---|---|
| `RDM_PUBLIC_BASE_URL` | **必填**。用户与 MCP 客户端访问的 HTTPS origin，无路径 |
| `RDM_HTTP_PORT` | `web` 容器映射到宿主机的端口，默认 `8080` |
| `RDM_DATABASE_URL` | 可选。空 = 容器内 SQLite（`rdm-data` 卷）；PostgreSQL 示例见下 |
| `POSTGRES_PASSWORD` | 可选（`postgres` profile） |

其他 `RDM_*` 变量（附件上限、Webhook 调优）见 [configuration.md](configuration.md)；
可在 `docker-compose.yml` 的 `rdm.environment` 中追加。

## 使用 PostgreSQL + ParadeDB

```bash
export POSTGRES_PASSWORD='change-me'
export RDM_DATABASE_URL='postgresql://rdm:change-me@db:5432/rdm'
docker compose --profile postgres up -d db
docker compose up -d rdm web
```

首次切换前请备份 SQLite 数据目录，并确认 `rdm init` / 启动迁移成功。

## TLS 与反向代理

Compose 只发布 `web` 容器的 HTTP 端口。生产环境在前端放一层 TLS：

- 企业负载均衡 / Kubernetes Ingress：把 `https://rdm.example.com` 转发到 `<host>:8080`，
  保留 `Host` 与 `X-Forwarded-Proto`。
- 宿主机 nginx：参考 [deploy/nginx/rdm.conf](../deploy/nginx/rdm.conf)，把 `proxy_pass`
  改为 `http://127.0.0.1:8080`（而不是 8765），并保留 `/api/v1/local/` 封禁规则。
- `RDM_PUBLIC_BASE_URL` 必须与实际访问的 HTTPS origin 完全一致；否则 OAuth 发现、
  登录回跳、附件链接都会错误。

内网没有公网 DNS 时，使用企业内网 CA 签发的证书同样可以；OAuth issuer 仍必须是 HTTPS。

## 数据、备份与升级

- 数据卷：`rdm-data`（SQLite 数据库、附件、workflow 配置、HMAC 密钥）。
- 备份：

  ```bash
  docker compose exec rdm tar -C /data -czf - . > rdm-data-backup.tar.gz
  ```

  使用 PostgreSQL 时改用 `pg_dump`，见 [runbook.md](runbook.md)。

- 升级：

  ```bash
  git pull
  docker compose build --pull
  docker compose up -d
  ```

  启动时自动执行数据库迁移；大版本升级前先备份。

## Owner 找回

恢复端点只在容器内回环可达，因此在后端容器内执行：

```bash
docker compose exec rdm rdm account recover-owner \
  --public-url "$RDM_PUBLIC_BASE_URL"
```

命令会输出一次性设置密码链接（7 天有效）。

## 单独构建镜像

```bash
docker build -f deploy/docker/backend.Dockerfile -t rdm-backend:0.1.0 .
docker build -f deploy/docker/web.Dockerfile -t rdm-web:0.1.0 .
```

后端镜像默认监听 `0.0.0.0:8765`，通过环境变量 `RDM_PUBLIC_BASE_URL` 提供公网 origin；
不要直接把 8765 发布到宿主机或公网，只允许 `web`/反向代理网络访问。

## 安全清单

- 只发布 `web` 端口；`rdm` 服务使用 compose 内部网络（`expose` 而非 `ports`）。
- 全链路 HTTPS；`RDM_PUBLIC_BASE_URL` 为 HTTPS origin。
- `/api/v1/local/` 在 nginx 与后端两层都受限，保持封禁规则。
- 数据卷与 `webhook-secret` / `attachment-secret` 按敏感数据备份与授权。
- 定期轮换 `POSTGRES_PASSWORD`，并通过 Web「我的设置 → 访问令牌」管理 PAT。
