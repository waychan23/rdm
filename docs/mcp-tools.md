# MCP 工具设计（v1）

> MCP 是本系统的核心界面。设计原则：**工具是硬约束，skill 是软引导**。
> 服务端：FastMCP 挂载于 `/mcp`（streamable HTTP），与 REST 共用 application service、DTO、错误码。

## 1. 设计原则

1. **状态推进只走具名工具**（`work_item_transition` / `sprint_start` / `sprint_close`），不存在"直接 update status"的通用工具。
2. **读响应自带下一步**：任何 item 级响应都带 `allowed_transitions`、`accountable_human`、`children_summary`，agent 不需要猜。
3. **错误即指引**：错误 `message` 必须包含"当前状态 → 允许去向 → 建议的下一步工具"；`details` 结构化（见 §5）。
4. **工具数量受控**（当前 28 个，下文逐字枚举为准）：查询/编辑通用化，状态推进具名化。新增/签名变更须在 architecture §17 记裁决。
5. **MCP 不传二进制**：附件只读列表/下载链接；上传走 OpenAPI/Web。
6. **返回精简**：列表默认 20 条、只回摘要字段（`display_id, kind, title, status, assignee, priority`）；详情用 `expand` 参数按需展开。
7. **幂等/并发**：写工具返回 `row_version`；冲突时返回 `CONFLICT_VERSION` 并附最新版本，agent 重读后重试。
8. 每个工具都有 `description`，写成给 agent 的操作说明（含"什么时候不该用它"）。

## 2. 统一响应信封

```json
{ "data": {...}, "meta": { "server_time": "...", "row_version": 7, "allowed_transitions": ["..."], "hint": "..." } }
```
错误：
```json
{ "error": { "code": "WORKFLOW_GATE_BLOCKED", "message": "...",
             "details": { "blocking_children": ["RDM-13"], "allowed_transitions": ["CANCELLED"], "hint": "..." } } }
```

## 3. 工具清单（28）

> 计数勘误（2026-10-24，architecture §16.24）：早期版本标称 26 个，实际枚举为 **27 个**——§3.2 标题写 7 但实列 8（`sprint_list`/`sprint_get` 在表中合占一行）。分节实数：3+8+7+4+3+2=27。
> **实现口径**：M1 交付 17 个；M2 已补齐全部 **27 个**（见 §16.51）；M5 新增 `project_bind` 后为 **28 个**，注册数测试改为精确匹配 28 个。
> **M5 变更**：新增 `project_bind`（architecture §17.80），总数 **28**；注册数测试改为精确匹配 28 个。

### 3.1 身份 / 上下文（4）【M1 全量 + M5】

| 工具 | 用途 | 关键入参 | 返回 |
|---|---|---|---|
| `whoami` 【M1】 | 当前身份与工作台：member、roles、项目、可接受 kind、未读信件数、我的未终态 items 数 | – | `{member, project, roles, unread_count, my_open_items, project_hint}` |
| `project_get` 【M1】 | 项目概况：成员摘要、当前 Sprint、各状态计数 | `project?` | 项目 + 成员 + sprint 摘要 |
| `workflow_get` 【M1】 | 拉取流程定义（状态、转换、终态、gate），**skill 引导 agent 时先调它** | `kind?` | `{kinds: {...}}` |
| `project_bind` 【M5】 | 校验/返回项目目录绑定；`project` 为空时返回可访问项目 options（带 `selection=user_choice_required`，禁止推荐）；不读写文件、无服务端状态 | `project?, current?` | `{project, options, selection, persist, change?, use_project}` |

### 3.2 查询（8）

| 工具 | 用途 | 关键入参 |
|---|---|---|
| `work_item_list` 【M1】 | 通用筛选：kind/status/assignee/sprint/parent/priority/keyword，分页 | `kind?, status?, assignee?, sprint?, parent?, q?, limit?, cursor?, include_deleted?` |
| `work_item_get` 【M1】 | 详情 + 子项 + 父项 + attachments（含正文内联图片）+ `allowed_transitions` + allowed parent/child kinds | `id` |
| `my_work_list` 【M2】 | 我的待办（assignee=me 且非终态，按 priority/display_no 排序）；传 `status` 时按状态精确过滤；传 `project` 时只列该项目 | `status?, project?` |
| `backlog_list` 【M2】 | ProductBacklog：**未进入任何 Sprint** 且非终态的 items（跨全部 sprint 链接差集） | `kind?, project?` |
| `sprint_list` / `sprint_get` 【M2】 | Sprint 列表（可按状态过滤）/ 详情（含 items 与 status_counts） | `status?, project?` / `id` |
| `member_list` 【M2】 | 项目成员（含 agent 的 manager、角色、可接 kinds、webhook 配置） | `type?, project?` |
| `comment_list` 【M2】 | 某个 item 的讨论，含每条评论挂载的附件与正文内联图片元数据 | `work_item_id, limit?, offset?` |

### 3.3 写入（工作项，7）【M1 全量】

| 工具 | 用途 | 关键入参 |
|---|---|---|
| `work_item_create` 【M1】 | 创建 epic/story/issue/task；`kind` 判别联合 schema，特型字段随 kind 不同 | `kind, title, parent?, description_md?, priority?, ...kind 特型` |
| `work_item_update` 【M1】 | 编辑字段（**不含 status**）；带 `row_version` 乐观锁 | `id, row_version, fields{...}` |
| `work_item_assign` 【M1】 | 指派 **assignee**（可为 agent）。M1 仅支持 `role=assignee`（无 reviewer/watcher 表，§16.22），传其他 role 返回 `VALIDATION_ERROR` | `id, member, note?` |
| `work_item_transition` 【M1】 | **唯一状态入口**；`reason?` 会写入事件 | `id, to, row_version, reason?` |
| `work_item_delete` 【M1】 | 级联软删（返回被删 id 列表） | `id` |
| `work_item_restore` 【M1】 | 恢复软删（校验父链，§16.26） | `id` |
| `comment_add` 【M1】 | 在 item 下留言，可 @member（触发站内信，§16.30）；M2 起支持 `attachment_ids`：先经 REST multipart 把附件传到工作项，再在发评论时把 id 一并提交（服务端同事务改绑到评论） | `work_item_id, body_md, reply_to?, attachment_ids?` |

### 3.4 Sprint（4）

| 工具 | 用途 |
|---|---|
| `sprint_create` 【M1】 | 建 Sprint（name/goal/起止/manager） |
| `sprint_manage` 【M2】 | `action: add_items|remove_item|update`（批量加入/移出/改字段）；CLOSED Sprint 仅可 remove_item，update 被拒 | `id, action, items?/item?, name?...` |
| `sprint_start` 【M1】 | 启动（置 active，校验同项目唯一 active，冲突报 `SPRINT_ACTIVE_EXISTS`） |
| `sprint_close` 【M1】 | 关闭；存在非终态 item 时 gate 拒绝；关闭前可用 sprint_manage remove_item 移走非终态项 |

### 3.5 信箱（3）

| 工具 | 用途 |
|---|---|
| `mailbox_check` 【M1】 | 增量拉取（`since` 游标 = 上一页最后一条 delivery id，默认未读，§16.28）；**必须传当前绑定项目的 `project`**，只查该项目 | `since?, unread_only?, limit?, project?` |
| `mailbox_send` 【M1】 | 发信：`to[]/cc[]`（member 或 group mailbox 名）、subject、body_md、`refs[]`（work_item ids）、`reply_to`（上一封信的 message_id，形成服务端回信链路） |
| `mailbox_mark_read` 【M2】 | 批量标记已读（传 delivery id，即信件条目中的 delivery_id） | `delivery_ids[]` |

### 3.6 产出物 / 附件 / 工作区（2）| 工具 | 用途 |
|---|---|
| `artifact_add` 【M2】 | 挂链接型产出物（设计稿/API 文档/仓库链接）；`owner_type` 仅暴露 project/item/comment（message 只走 REST），URL 限 http(s) | `owner_type, owner, kind, label, url` |
| `attachment_list` 【M2】 | 列附件元数据 + `download_url` + 短时 `fetch_url`（不传二进制）；`owner_type=project` 时 `owner` 可省略（项目级内联图片）。**上传/下载/删除走 REST**：`POST /projects/<key>/attachments`（multipart：file + owner_type + owner_ref? + state?，20MB 上限、可执行类型黑名单）、`GET /attachments/<id>/download`、`DELETE` | `owner?, owner_type?, project?` |

> 未列入 MCP 工具：项目/成员/token/workspace 的写操作（v1 走 Web/OpenAPI，保持人类掌控）；事件查询（v1 只记录，后续再加）。

**附件图片约定（§17.83/§17.87）**：Web 编辑器粘贴的图片是 `owner_type=project` 的附件，正文以
`/api/v1/attachments/{id}/download` 内嵌；保存后 `state=active`，未保存的是 `state=temp`。
`work_item_get`、`comment_list`、`attachment_list` 返回的附件都带短时 `fetch_url`
（15 分钟 HMAC 签名，可直接 `curl`，无需 Bearer）；PAT 客户端也可用 `download_url` + Bearer。
`fetch_url` 只读、过期失效，不要缓存或转存。

## 4. 关键工具 Schema（节选）

```python
class WorkItemCreateIn(BaseModel):
    project: str | None  # 缺省取 actor 唯一项目；多项目必须显式传（见 §4.1）
    kind: Literal["epic", "story", "issue", "task"]
    title: str
    parent: str | None = None  # display_id
    description_md: str | None = None
    priority: int = 0
    assignee: str | None = None  # member name 或 id
    sprint: str | None = None
    # kind=story
    acceptance_criteria_md: str | None = None
    # kind=issue
    severity: Literal["blocker", "critical", "major", "minor", "trivial"] | None = None
    environment: str | None = None
    repro_steps_md: str | None = None
    expected_behavior_md: str | None = None
    actual_behavior_md: str | None = None
    source_story: str | None = None
    # kind=task
    task_type: (
        Literal[
            "product_design",
            "ux_design",
            "frontend",
            "backend",
            "fullstack",
            "qa",
            "release",
            "docs",
            "other",
        ]
        | None
    ) = None
    est_work_hours: float | None = None
    code_branch: str | None = None
```
服务端按 `kind` 做**交叉校验**（例如 story 传 severity → `VALIDATION_ERROR`，并提示"severity 仅适用于 issue"），并把该报错写进给 agent 的提示。

```python
class TransitionIn(BaseModel):
    id: str
    to: str  # 状态枚举
    row_version: int
    reason: str | None = None  # 记入事件 payload，供审计
```

`work_item_transition` 成功响应示例：
```json
{ "data": { "id": "RDM-13", "kind": "story", "status": "TO_TEST", "row_version": 9 },
  "meta": { "allowed_transitions": ["DONE","IN_PROGRESS","CANCELLED"],
            "children_summary": { "total": 3, "terminal": 2 },
            "hint": "进入 DONE 前需所有子任务终态：RDM-16 仍为 IN_PROGRESS" } }
```

### 4.1 项目上下文解析（M5）

MCP 请求不携带 cwd；绑定事实源是客户端工作区根目录的 `.rdm/project.json`，服务端**不读该文件、不存服务端状态**。

解析优先级：

```text
工具显式 project 参数
  > actor 的唯一项目（N=1）
  > PROJECT_REQUIRED（details.options + details.recovery）
```

- agent 开工时读取 `.rdm/project.json`；有 `project` 就调用 `project_bind(project=KEY)` 校验，并在项目级工具上显式传 `project=KEY`。
- 没有文件时调用 `project_bind()` 拿 `options`，让用户选择一次；返回的 `selection.mode=user_choice_required` 明确禁止 agent 推荐或代选（不得根据信箱、未读数、最近活动、角色推断）。`project_bind(project=KEY)` 成功后把返回的 `persist.content` 写入 `.rdm/project.json`。
- 改绑用 `project_bind(project=NEW, current=OLD)`；返回 `change` 与 `requires_confirmation=true`，用户确认后再覆盖文件。校验失败不覆盖旧文件。
- 单次跨项目操作直接传 `project=OTHER`，不要改绑文件。
- **绑定后只处理该项目的信件/工作项**：不要遍历 `whoami.projects`，不要查询、处理或建议处理其他项目的内容，除非用户明确要求。`mailbox_check` / `mailbox_send` / `my_work_list` 都应带 `project=<绑定 KEY>`。
- `PROJECT_REQUIRED` / `PROJECT_BINDING_INVALID` 的 `details.recovery` 写明 agent 自愈步骤：读文件 → `project_bind` → 带 `project` 重试；不要让用户重新执行 integrate 或手输项目 ID。

## 5. 错误码 → agent 指引

| code | message 模板（含下一步） |
|---|---|
| `WORKFLOW_ILLEGAL_TRANSITION` | `不能从 {from} 到 {to}。允许：{allowed}。若目标是发起测试，用 work_item_transition 到 TO_TEST。` |
| `WORKFLOW_GATE_BLOCKED` | `{item} 不能进入 {to}：{blocking}。先完成/取消子项，或用 comment_add 通知负责人。` |
| `CONFLICT_VERSION` | `该对象已被 {actor} 修改（当前版本 {n}）。先 work_item_get 重读，再重试。` |
| `ALREADY_ASSIGNED` | `{item} 已被 {member} 认领。若需协作，用 mailbox_send 联系其 accountable_human。` |
| `FORBIDDEN` | `当前身份 {member} 不能执行该操作；需要 Owner/Manager，可用 mailbox_send 请求协助。` |
| `VALIDATION_ERROR` | `字段 {field} 不适用于 kind={kind}。该 kind 的字段见 workflow_get / work_item_get。` |
| `PROJECT_REQUIRED`（details.code） | `当前调用缺少项目上下文。读取工作区 .rdm/project.json；有 project 就调用 project_bind 并带 project=KEY 重试；没有就把 details.options 交给用户选择一次。` |
| `PROJECT_BINDING_INVALID`（details.code） | `目录绑定的项目 {key} 不可用（不存在/无权限）。把 details.options 交给用户重新选择一次，调用 project_bind(project=NEW, current=OLD)，确认后覆盖 .rdm/project.json。不要静默切换项目。` |

## 6. 与 SKILL 的配套

`rdm-workflow` 与 `rdm-mailbox` 两个随包 skill（`rdm skills install` 安装）分别承担工作流与信箱的软引导，内容大纲：

1. 开工前：先按 §4.1 读取/建立 `.rdm/project.json` 并调用 `project_bind`；之后 `whoami` → `mailbox_check(project=<KEY>)` → `my_work_list(project=<KEY>)`（三步定工作上下文；`work_item_list(assignee="me", project=<KEY>)` 等价）。
2. 认领：确认 `assignee` 是自己 → 若可认领用 `work_item_update` 或 `work_item_assign` → 状态 `IN_PROGRESS`。
3. 推进：**每次改状态前先看 `allowed_transitions`**；gate 被拒时不要去试别的转换，而是看 `blocking_children` 并处理/通知。
4. 协作：跨 agent 传递信息一律走 `mailbox_send`（附 `refs`），不要靠 commit message/代码注释。
5. 完成：`actual_work_hours` 回填 → `TO_REVIEW` → 等人类 reviewer → `DONE`（**agent 不得自行把 TO_REVIEW 推成 DONE**）。
6. 异常：报错按 §5 的 hint 处理；连续两次同错 → `mailbox_send` 给 accountable_human，附错误原文。
7. 禁止事项：不要猜 id、不要绕过 `work_item_transition`、不要重复 `mailbox_send` 同一内容、不要修改他人负责的 item 状态。

## 7. 工具命名与注册约定

- 命名：`资源_动作`（`work_item_*`、`sprint_*`、`mailbox_*`），全小写蛇形；无前缀 `rdm_`（server 名已隔离）。
- 注册：`interfaces/mcp/tools/<resource>.py` 每文件一个模块，`register(mcp, container)` 函数（container 用于开 UoW）；工具函数只做 pydantic 入参 → 调 service → 包信封。
- 测试：每个工具至少一条 happy path + 一条错误码映射测试；`workflow_get` 的工具输出必须与 REST `/api/v1/workflow` 完全一致（同一函数生成）。
- 工具总数当前 28（见 §3）；新增或签名变更必须在 `docs/architecture.md` §17 记裁决，不做无理由扩张。
