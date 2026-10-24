---
name: rdm-workflow
description: rd-manager（rdm）工作流操作规范。当需要通过 rdm MCP 工具认领任务、推进工作项状态、处理 gate 阻塞、与其他 human/agent 协作通信时使用。
---

# rdm 工作流操作规范

你通过 rdm 的 MCP 工具在一个受管控的工作流系统中干活。硬约束（状态机、gate、权限）在服务端，你无法绕过；本规范告诉你**何时该调哪个工具、出错时怎么办**。

## 1. 开工三步：建立上下文

每次开始工作前按顺序调用：

1. `whoami` —— 确认身份、角色、未读信件数（unread_count）和我的未终态工作项数。
2. `mailbox_check` —— 拉取分配给你的信件与上下文（默认只拉未读；带 `since` 游标做增量拉取，把上一次返回的 `next_cursor` 传回去）。
3. `work_item_list`（参数 `assignee="me"`）—— 列出分配给你的未终态工作项（M1 没有 my_work_list 工具，`"me"` 是保留字，服务端解析为你的成员 id）。

不要在没有上下文时直接改状态或发信。

## 2. 认领工作项

1. 先 `work_item_get`（id 接受 `KEY-42` 显示 ID 或 ULID）确认 `assignee` 与当前状态。
2. 未指派且该由你做：`work_item_assign` 把 assignee 设为自己（M1 只支持 assignee，传 reviewer/watcher 会报 VALIDATION_ERROR）。
3. 认领后立即 `work_item_transition` 转到 `IN_PROGRESS`（task）或对应 kind 的"进行中"状态。
4. 若认领时返回 `ALREADY_ASSIGNED`，说明被别人抢走/指派了——不要争，用 `mailbox_send` 联系其 accountable_human。

## 3. 推进状态：只走 work_item_transition

- **唯一的状态入口是 `work_item_transition`**，永远不要用 work_item_update 改 status（也改不了）。
- **每次转状态前先看返回里的 `allowed_transitions`**，只转其中列出的状态；别靠记忆猜状态名。
- 调用必须带 `work_item_get` 返回的最新 `row_version`；返回 `CONFLICT_VERSION` 表示有人先改过，重新 get 后再试。
- 成功返回的 meta 含 `allowed_transitions`、`children_summary`、`hint`，是下一步的操作指引。
- **gate 被拒（`WORKFLOW_GATE_BLOCKED`）时不要去试别的转换**：读 `details.blocking_children`（仍未终态的子项 display_id 列表），先完成/取消这些子项，或用 `comment_add`/`mailbox_send` 通知负责人，然后重试同一转换。

## 4. 协作：一切走信箱

- 跨 human/agent 传递任何需要对方知道的信息，一律 `mailbox_send`，并用 `refs` 附上相关工作项 id。**不要靠 commit message、代码注释或口头约定传递工作信息。**
- 收件人 `to/cc` 可传成员 name/id 或 group 信箱名；发信前如不确定名字，先在项目上下文中确认，不要猜。
- 在工作项下发用 `comment_add`；评论里 `@成员名` 会自动给对方发一封站内信（找不到名字或重名时静默忽略）。
- 回复信件使用 `reply_to`，保持线程。

## 5. 完成工作

1. task 完成后先回填实际工时（`work_item_update` 改 `actual_work_hours` 等特型字段）。
2. `work_item_transition` 转到 `TO_REVIEW`。
3. **停住。agent 不得自行把 TO_REVIEW 推成 DONE**——v1 没有 reviewer 字段，DONE 由人类 reviewer（或 owner/manager）完成。转完 TO_REVIEW 后用 `mailbox_send` 通知你的 accountable_human 进行验收。
4. Story/Issue/Epic 进入终态有 gate：所有直接子项必须先处于各自 kind 的终态；issue 关闭还要求至少有 1 个子任务（见 §3 的 blocking_children）。

## 6. 异常处理

- 一切错误都是结构化信封 `{"error": {"code", "message", "details"}}`：按 `message` 的中文指引行动，`details`（如 allowed_transitions、blocking_children、current_version）给具体数据。
- `FORBIDDEN`：你的身份无权做此事（worker 只能流转分配给自己的 item；sprint 创建/启动/关闭仅 owner/manager）——用 mailbox_send 请求有权限的人协助，不要重试。
- `NOT_FOUND`：id 错或不属于当前项目；重新 `work_item_get` / 查列表确认，**不要猜 id**。
- **同一个错误连续出现两次**：停止重试，`mailbox_send` 给 accountable_human，附上错误原文与你尝试的操作。

## 7. 禁止事项

- 不要猜工作项/成员 id；先查询。
- 不要尝试绕过 `work_item_transition` 改状态。
- 不要修改分配给他人的工作项状态（会得 FORBIDDEN）。
- 不要重复 `mailbox_send` 同一内容；对同一事项用 reply_to 回信。
- 不要在 TO_REVIEW 后自行推进到 DONE。
- 不要忽略 gate 阻塞去尝试其他转换路径——状态机没有"绕路"。
