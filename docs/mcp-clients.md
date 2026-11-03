# MCP 客户端接入

rdm 通过一个 Streamable HTTP endpoint 暴露 35 个 MCP 工具：`<origin>/mcp`
（本地默认 `http://127.0.0.1:8765/mcp`，生产为 `https://<public-origin>/mcp`）。
支持两种认证：**原生 OAuth 2.1**（浏览器授权）与 **Bearer PAT**（静态令牌，适合 CI/无浏览器环境）。

## 方式一：OAuth（推荐给人类使用者）

```bash
rdm integrate mcp                         # 写入 claude / codex / opencode 的用户级配置
rdm integrate mcp --target claude         # 只写某一家
rdm integrate mcp --url https://rdm.example.com/mcp
```

- 客户端首次连接时打开浏览器，完成 Authorization Code + PKCE 流程，并在同意页选择
  **以本人还是自己管理的某个 agent 身份**工作。
- OAuth discovery 使用 `/.well-known/oauth-authorization-server` 等根路径，nginx 必须反代
  `/.well-known/`、`/mcp`、`/api/`。
- 更换 `RDM_PUBLIC_BASE_URL` 或域名后，客户端需要重新授权（旧 issuer 不再匹配）。

## 方式二：PAT（推荐给 CI、无浏览器环境、目录级身份绑定）

PAT 只能由本人在 Web「我的设置 → 访问令牌」或 `rdm me token-create` 创建；
可指定使用身份为本人或自己管理的 agent。管理员不能代签，只能撤销。

```bash
export RDM_TOKEN=rdm_pat_...
rdm integrate mcp --method token
```

项目级绑定（一个代码库目录 = 一个身份）：

```bash
cd ~/repo/demo-frontend
rdm integrate mcp --scope project --method token --member-token "$FRONTEND_PAT"
```

- 会给 claude（`~/.claude.json` 按绝对路径键控）与 opencode（`<cwd>/.opencode/opencode.json`）
  写入同一个 token，并把 `.opencode/` 追加进该库的 `.gitignore`；**token 不进入代码库**。
- codex 没有项目级配置，使用 `--scope user`。
- 已有绑定时需要 `--force` 轮换。

## 通用客户端手工配置

任何支持 Streamable HTTP + Bearer 的客户端都可以直接配置：

```json
{
  "mcpServers": {
    "rdm": {
      "type": "http",
      "url": "https://rdm.example.com/mcp",
      "headers": { "Authorization": "Bearer ${RDM_TOKEN}" }
    }
  }
}
```

OAuth 客户端只需 URL，不需要预置 token；授权由客户端发现流程完成。

## 安装 rdm skills（给 agent 的工作流规范）

[Skill 内容随 wheel 发布](../src/rdm/resources/skills/)，安装到 agent CLI：

```bash
rdm skills install --target claude                    # ~/.claude/skills/rdm-workflow/…
rdm skills install --target codex
rdm skills install --target opencode
rdm skills install --target claude --scope project --cwd .   # 写入 <cwd>/.claude/skills
rdm skills install --target claude --skill rdm-mailbox       # 只装一个（可重复）
```

卸载：

```bash
rdm uninstall mcp --target claude
rdm uninstall skills --target claude
rdm uninstall all
```

## 项目绑定：`.rdm/project.json`

agent 在目录内工作时，通过工作区根的 `.rdm/project.json` 固定项目：

```json
{ "version": 1, "project": "RDM" }
```

- 该文件不含密钥，是否提交由团队决定（每个开发者本地选择时加入 `.gitignore`）。
- MCP 工具的项目级参数（`work_item_list`、`mailbox_check` 等）应显式传 `project="RDM"`。
- `project_bind` 用于校验绑定或列出可选项；绑定变化需先确认再覆盖文件。

## 排障

| 现象 | 处理 |
|---|---|
| 连接超时 / 502 | 本机开着系统代理时，loopback 流量可能被代理拦截：`export NO_PROXY=127.0.0.1,localhost,::1` |
| 401 / `invalid_token` | PAT 过期或被撤销：重新创建并更新客户端配置；OAuth 则重新授权 |
| OAuth discovery 404 | nginx 没有反代 `/.well-known/`，或 `RDM_PUBLIC_BASE_URL` 配成了内网/回环地址 |
| 工具调用报 `PROJECT_REQUIRED` | 按错误信封的 `details.recovery` 读取 `.rdm/project.json` 后重试；不要手输项目 ID |
| 改了域名后旧客户端失败 | 重新执行 `rdm integrate mcp --url https://<new-origin>/mcp --force` |

工具清单与错误码见 [mcp-tools.md](mcp-tools.md)；agent 工作流规范见随包安装的
`rdm-workflow` / `rdm-mailbox` skills。
