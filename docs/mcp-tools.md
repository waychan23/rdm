# MCP 工具设计（v1）

> MCP 是本系统的核心界面。设计原则：**工具是硬约束，skill 是软引导**。
> 服务端：FastMCP 挂载于 `/mcp`（streamable HTTP），与 REST 共用 application service、DTO、错误码。

## 1. 设计原则

1. **状态推进只走具名工具**（`work_item_transition` / `sprint_start` / `sprint_close`），不存在"直接 update status"的通用工具。
2. **读响应自带下一步**：任何 item 级响应都带 `allowed_transitions`、`accountable_human`、`children_summary`，agent 不需要猜。
3. **错误即指引**：错误 `message` 必须包含"当前状态 → 允许去向 → 建议的下一步工具"；`details` 结构化（见 §5）。
4. **工具数量受控**（目标 26 个）：查询/编辑通用化，状态推进具名化。
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

## 3. 工具清单（26）

### 3.1 身份 / 上下文（3）

| 工具 | 用途 | 关键入参 | 返回 |
|---|---|---|---|
| `whoami` | 当前身份与工作台：member、roles、项目、可接受 kind、未读信件数、我的未终态 items 数 | – | `{member, project, roles, unread_count, my_open_items}` |
| `project_get` | 项目概况：成员摘要、当前 Sprint、各状态计数 | `project?` | 项目 + 成员 + sprint 摘要 |
| `workflow_get` | 拉取流程定义（状态、转换、终态、gate），**skill 引导 agent 时先调它** | `kind?` | `{kinds: {...}}` |

### 3.2 查询（7）

| 工具 | 用途 | 关键入参 |
|---|---|---|
| `work_item_list` | 通用筛选：kind/status/assignee/sprint/parent/priority/keyword，分页 | `kind?, status?, assignee?, sprint?, parent?, q?, limit?, cursor?, include_deleted?` |
| `work_item_get` | 详情 + 子项 + 评论 + artifacts + attachments + `allowed_transitions` | `id, expand?` |
| `my_work_list` | 我的待办（assignee=me 且非终态），按 priority/rank 排序 | `status?` |
| `backlog_list` | ProductBacklog 视图：未入 Sprint、未终态 items | `kind?, priority_min?` |
| `sprint_list` / `sprint_get` | Sprint 列表 / 详情（含 items 与状态统计） | – / `id` |
| `member_list` | 项目成员（含 agent 的 manager） | `type?` |
| `comment_list` | 某个 item 的讨论 | `work_item_id` |

### 3.3 写入（工作项，7）

| 工具 | 用途 | 关键入参 |
|---|---|---|
| `work_item_create` | 创建 epic/story/issue/task；`kind` 判别联合 schema，特型字段随 kind 不同 | `kind, title, parent?, description_md?, priority?, ...kind 特型` |
| `work_item_update` | 编辑字段（**不含 status**）；带 `row_version` 乐观锁 | `id, row_version, fields{...}` |
| `work_item_assign` | 指派 assignee / reviewer / watcher（可为 agent） | `id, role, member, note?` |
| `work_item_transition` | **唯一状态入口**；`reason?` 会写入事件 | `id, to, row_version, reason?` |
| `work_item_delete` | 级联软删（返回被删 id 列表） | `id` |
| `work_item_restore` | 恢复软删（校验父链） | `id` |
| `comment_add` | 在 item 下留言，可 @member（触发站内信）、可挂已有附件 | `work_item_id, body_md, reply_to?, mention?` |

### 3.4 Sprint（4）

| 工具 | 用途 |
|---|---|
| `sprint_create` | 建 Sprint（name/goal/起止/manager） |
| `sprint_manage` | `action: add_items|remove_item|update`（批量加入/移出/改字段） |
| `sprint_start` | 启动（置 active，校验同项目唯一 active） |
| `sprint_close` | 关闭；若存在非终态 item，必须显式给 `move_out_items` 或 `allow_incomplete=false` 的专门标记，否则 gate 拒绝 |

### 3.5 信箱（3）

| 工具 | 用途 |
|---|---|
| `mailbox_check` | 增量拉取（`since` 游标，默认未读）；返回发件人、标题、摘要、关联 item id |
| `mailbox_send` | 发信：`to[]/cc[]`（member 或 group mailbox 名）、subject、body_md、`refs[]`（work_item ids） |
| `mailbox_mark_read` | 批量标记已读 |

### 3.6 产出物 / 附件 / 工作区（2）

| 工具 | 用途 |
|---|---|
| `artifact_add` | 挂链接型产出物（设计稿/API 文档/仓库链接）到 item/comment/project |
| `attachment_list` | 列附件元数据 + 下载 URL（不传二进制） |

> 未列入 MCL 工具：项目/成员/token/workspace 的写操作（v1 走 Web/OpenAPI，保持人类掌控）；事件查询（v1 只记录，后续再加）。

## 4. 关键工具 Schema（节选）

```python
class WorkItemCreateIn(BaseModel):
    project: str | None          # 缺省取 RDM_PROJECT
    kind: Literal["epic","story","issue","task"]
    title: str
    parent: str | None = None    # display_id
    description_md: str | None = None
    priority: int = 0
    assignee: str | None = None  # member name 或 id
    sprint: str | None = None
    # kind=story
    acceptance_criteria_md: str | None = None
    # kind=issue
    severity: Literal["blocker","critical","major","minor","trivial"] | None = None
    environment: str | None = None
    repro_steps_md: str | None = None
    expected_behavior_md: str | None = None
    actual_behavior_md: str | None = None
    source_story: str | None = None
    # kind=task
    task_type: Literal["product_design","ux_design","frontend","backend","fullstack","qa","release","docs","other"] | None = None
    est_work_hours: float | None = None
    code_branch: str | None = None
```
服务端按 `kind` 做**交叉校验**（例如 story 传 severity → `VALIDATION_ERROR`，并提示"severity 仅适用于 issue"），并把该报错写进给 agent 的提示。

```python
class TransitionIn(BaseModel):
    id: str
    to: str                      # 状态枚举
    row_version: int
    reason: str | None = None    # 记入事件 payload，供审计
```

`work_item_transition` 成功响应示例：
```json
{ "data": { "id": "RDM-13", "kind": "story", "status": "TO_TEST", "row_version": 9 },
  "meta": { "allowed_transitions": ["DONE","IN_PROGRESS","CANCELLED"],
            "children_summary": { "total": 3, "terminal": 2 },
            "hint": "进入 DONE 前需所有子任务终态：RDM-16 仍为 IN_PROGRESS" } }
```

## 5. 错误码 → agent 指引

| code | message 模板（含下一步） |
|---|---|
| `WORKFLOW_ILLEGAL_TRANSITION` | `不能从 {from} 到 {to}。允许：{allowed}。若目标是发起测试，用 work_item_transition 到 TO_TEST。` |
| `WORKFLOW_GATE_BLOCKED` | `{item} 不能进入 {to}：{blocking}。先完成/取消子项，或用 comment_add 通知负责人。` |
| `CONFLICT_VERSION` | `该对象已被 {actor} 修改（当前版本 {n}）。先 work_item_get 重读，再重试。` |
| `ALREADY_ASSIGNED` | `{item} 已被 {member} 认领。若需协作，用 mailbox_send 联系其 accountable_human。` |
| `FORBIDDEN` | `当前身份 {member} 不能执行该操作；需要 Owner/Manager，可用 mailbox_send 请求协助。` |
| `VALIDATION_ERROR` | `字段 {field} 不适用于 kind={kind}。该 kind 的字段见 workflow_get / work_item_get。` |

## 6. 与 SKILL 的配套

`rdm-workflow/SKILL.md`（随包分发，`rdm skills install` 安装）承担"何时用哪个工具"的软引导，内容大纲：

1. 开工前：`whoami` → `mailbox_check` → `my_work_list`（三步定工作上下文）。
2. 认领：确认 `assignee` 是自己 → 若可认领用 `work_item_update` 或 `work_item_assign` → 状态 `IN_PROGRESS`。
3. 推进：**每次改状态前先看 `allowed_transitions`**；gate 被拒时不要去试别的转换，而是看 `blocking_children` 并处理/通知。
4. 协作：跨 agent 传递信息一律走 `mailbox_send`（附 `refs`），不要靠 commit message/代码注释。
5. 完成：`actual_work_hours` 回填 → `TO_REVIEW` → 等人类 reviewer → `DONE`（**agent 不得自行把 TO_REVIEW 推成 DONE**）。
6. 异常：报错按 §5 的 hint 处理；连续两次同错 → `mailbox_send` 给 accountable_human，附错误原文。
7. 禁止事项：不要猜 id、不要绕过 `work_item_transition`、不要重复 `mailbox_send` 同一内容、不要修改他人负责的 item 状态。

## 7. 工具命名与注册约定

- 命名：`资源_动作`（`work_item_*`、`sprint_*`、`mailbox_*`），全小写蛇形；无前缀 `rdm_`（server 名已隔离）。
- 注册：`interfaces/mcp/tools/<resource>.py` 每文件一个模块，`register(mcp)` 函数；工具函数只做 pydantic 入参 → 调 service → 包信封。
- 测试：每个工具至少一条 happy path + 一条错误码映射测试；`workflow_get` 的工具输出必须与 REST `/api/v1/workflow` 完全一致（同一函数生成）。
- 工具总数预算 26，超预算需先删/合并再新增。
