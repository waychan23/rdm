# 运维手册（rdm）

> 适用：单进程、单写者、loopback-only 的自托管部署。数据目录默认 `~/rdm-data`，
> 可用 `--data-dir` / `RDM_DATA_DIR` 覆盖。数据库默认 SQLite；设置
> `RDM_DATABASE_URL` 后改用 PostgreSQL（要求 ParadeDB `pg_search` 扩展，§17.114）。
> 所有命令在仓库根执行。

## 1. 日常启停

```bash
uv run rdm serve                 # 前台；Ctrl-C 优雅停止
uv run rdm doctor                # 全绿再继续操作
uv run rdm workflow validate     # workflow.json5 改动后必跑
```

`rdm serve` 启动时会自动 `initialize_data_dir` + `alembic upgrade head`。
非回环 `--host` 会被拒绝；远程访问请用 SSH 端口转发或自带鉴权的反向代理。

PostgreSQL 模式（可选）：

```bash
export RDM_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/rdm
uv run rdm serve
```

数据库必须是 ParadeDB 镜像或已安装 `pg_search` 并设置
`shared_preload_libraries='pg_search'`；`rdm init/serve` 会在启动前检查扩展。

## 2. 备份与恢复（手工流程）

当前版本没有内置 `rdm backup` 命令，按以下步骤做一致性备份：

```bash
# 1) 停服（确保没有写入）
# 2) 拷贝数据库（SQLite 文件 + WAL；停服后 WAL 已合并）
cp -a "$RDM_DATA_DIR/rdm.db" "/backup/rdm-$(date +%F).db"
# 3) 拷贝附件与密钥
tar -C "$RDM_DATA_DIR" -czf "/backup/rdm-files-$(date +%F).tgz" \
  projects webhook-secret attachment-secret
# 4) 记录 schema 版本
uv run rdm db status | tee "/backup/rdm-$(date +%F).version"
```

恢复：停服 → 用备份覆盖 `rdm.db` 与 `projects/` → `uv run rdm db upgrade` →
`uv run rdm doctor` → 起服。跨版本恢复时先确认备份的 Alembic revision 不高于当前包。

### PostgreSQL 备份

```bash
# 1) 停服（或至少停止写入）
# 2) 逻辑备份数据库
pg_dump --format=custom --file="/backup/rdm-$(date +%F).dump" "$RDM_DATABASE_URL"
# 3) 附件与密钥仍在 data-dir
tar -C "$RDM_DATA_DIR" -czf "/backup/rdm-files-$(date +%F).tgz" \
  projects webhook-secret attachment-secret
# 4) 记录 schema 版本
uv run rdm db status | tee "/backup/rdm-$(date +%F).version"
```

恢复：停服 → `pg_restore --clean --if-exists -d "$RDM_DATABASE_URL" <dump>` →
覆盖 `projects/` 等文件 → `uv run rdm db upgrade` → `rdm doctor` → 起服。

> 升级前务必做一次备份。M5 的 0007 迁移只接受空库重建；不要把旧库直接带到 M5 之后。

## 3. 升级与回滚

```bash
# 升级
pnpm -C web-next install --frozen-lockfile --ignore-scripts
pnpm -C web-next build
uv sync                          # PostgreSQL 模式加 --extra postgres
uv run rdm serve                  # 自动迁移
uv run rdm doctor
```

回滚：停服 → 恢复升级前备份 → 切回旧版本代码 → `uv run rdm db downgrade <rev>`（如需要）→ 起服。
注意 downgrade 只保证 schema，不保证业务数据可逆；优先用备份恢复。

## 4. 常见故障

| 现象 | 排查 |
|---|---|
| 启动报 `database is locked` | 确认没有第二个 `rdm serve`；`rdm doctor` 看 DB 版本；等待 writer 锁释放后重试 |
| 登录后无限 401/刷新 | 检查浏览器 token 是否过期；确认 `/authorize` scope 为 `web`；必要时清 localStorage 重新登录 |
| agent 连不上 MCP | `rdm doctor` 看 endpoint/OAuth metadata；确认 `/mcp` 与 `RDM_TOKEN`；客户端配置见 README |
| Webhook 未送达 | `rdm doctor` 看 outbox 积压；检查 `notify_webhook` 与 IM 机器人 URL；失败按 1m/5m/15m 重试，4 次后 failed |
| 搜索无结果 | SQLite：确认 FTS 表存在（迁移 0019），<3 字符走 LIKE；PostgreSQL：确认 `pg_search` 扩展与 `ix_search_index_bm25` 存在，1–2 字符走 ILIKE |
| 附件打不开 | `rdm doctor` 的 attachments 检查；确认 `projects/<id>/attachments` 权限与磁盘空间 |
| 前端白屏 | 打开浏览器控制台；查看 `rdm serve` 日志 request_id；确认 `src/rdm/resources/web-next-dist/index.html` 存在 |
| 磁盘持续增长 | temp 附件尚无自动 GC（M7 仍未做）；手工清理 24h 前 `state=temp` 且未被引用的文件与行；事件/outbox 无自动保留策略 |

## 5. 安全边界

- 服务只监听 127.0.0.1；远程访问用 SSH 隧道，不要直接暴露 8765。
- data-dir 内 `webhook-secret`、`attachment-secret` 为 0600；`rdm.db` 与附件依赖部署目录权限，建议 `chmod 700` 数据目录。
- PAT 由本人创建；管理员只能批量撤销。`/docs` 仍默认公开（loopback 内），反向代理时请加鉴权。
- 备份文件含全部业务数据与密钥，按敏感数据保管。

## 6. 诊断命令速查

```bash
uv run rdm doctor --json
uv run rdm db status
uv run rdm workflow validate
uv run rdm account recover-owner          # 服务需在本机运行
tail -f "$RDM_DATA_DIR"/...               # 日志走 stdout（JSON 行）
```
