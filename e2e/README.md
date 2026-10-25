# e2e — 双 CLI 端到端验收（S1–S10）

用**真实的 agent CLI**（`claude -p` / `opencode run`，非 MCP 客户端模拟）驱动
rdm，验收 `docs/plan.md §4` 的十个场景。断言落在临时 sqlite 的投影与事件上。

## 前置

- Python 3.13，已 `uv sync`（必须用 `uv run` 运行，系统 python3 版本可能过旧）
- 本机已安装并登录至少一个 CLI：`claude`（2.1+）或 `opencode`（1.18+）
- CLI 能访问模型（需要各自的 API 账号/额度）；网络本地回环，NO_PROXY 已自动设置

## 运行

```bash
# 两个 CLI 各跑一遍全部场景（每个 CLI 全新 data dir + 随机端口的 rdm serve）
uv run python e2e/run_e2e.py

# 只跑 claude、只跑部分场景、保留现场
uv run python e2e/run_e2e.py --cli claude --scenarios S1,S4,S5 --no-cleanup
```

- 未安装的 CLI 整体 SKIP（exit 0）；`--strict` 下 SKIP 视为失败（供 CI/nightly）
- 任一断言失败 exit 1；一个场景失败不影响后续场景执行

## 产物（`e2e/out/<时间戳>/<cli>/`）

- `server.log`：rdm serve 日志
- `prompts/`：每次 headless 调用的强约束 prompt 与 CLI 输出
- `events-<KEY>.json`：该场景项目的事件类型集合
- `data/`：运行后默认删除（`--no-cleanup` 保留）

## 设计

- **管理动作走 REST**（建项目/成员/签发 token），**agent 动作走 CLI→MCP**
- 每个成员绑定到唯一临时目录（`rdm integrate mcp project-scope` 同款绑定函数），
  目录内安装随包 skill；claude 绑定写 `~/.claude.json` 的项目键（运行后清理），
  opencode 写临时目录 `.opencode/opencode.json`
- 每个 prompt 只给确定 id，指示先查工具（member_list/work_item_get）再动手，
  完成后用一句话报告结果；断言以 DB/事件为准，不依赖自然语言输出格式
- 每步后轮询 sqlite（默认 120s），未达成则**原 prompt 整体重试一次**，仍失败判 FAIL
- S9 用线程内 mock webhook 验 HMAC 头与重试计数；S10 用 `rdm doctor --json` 断言
- 纯 REST 的场景（S8/S10 部分）可在没有 LLM 的情况下用于验证服务端链路
