---
name: rdm-workflow
description: rd-manager（rdm）工作流操作规范。当需要通过 rdm MCP 工具认领任务、推进工作项状态、处理 gate 阻塞、与其他 human/agent 协作通信时使用。
---

# rdm 工作流操作规范

你通过 rdm 的 MCP 工具在一个受管控的工作流系统中干活。硬约束（状态机、gate、权限）在服务端，你无法绕过；本规范告诉你**何时该调哪个工具、出错时怎么办**。

## 0. 项目上下文（每次会话先做）

1. 读取当前工作区根目录的 `.rdm/project.json`。
2. 有 `{"version": 1, "project": "KEY"}`：调用 `project_bind(project="KEY")` 校验；之后所有项目级工具显式传 `project="KEY"`。不要询问用户。
3. 没有：调用 `project_bind()` 拿到 `options`，把 `key/name/roles` 展示给用户**自己选择**；不要推荐，不要根据信箱有无信、未读数、最近活动或角色推断。调用 `project_bind(project="KEY")`，把返回的 `persist.content` 写入 `.rdm/project.json`；之后项目级工具传 `project="KEY"`。
   带 `project` 参数的工具包括 `work_item_list`、`backlog_list`、`sprint_list`、`member_list`、`work_item_create`、`sprint_create`、`mailbox_check`、`mailbox_send`、`artifact_add`、`attachment_list`、`project_get`；按 id 操作的工具（如 `work_item_get`、`work_item_transition`、`sprint_manage`）不需要传。
4. 收到 `PROJECT_REQUIRED` / `PROJECT_BINDING_INVALID` 时，按 `details.recovery` 自愈：读文件 → `project_bind` → 带 `project` 重试。**不要**要求用户重新执行 `rdm integrate`，**不要**让用户手输项目 ID。
5. 改绑：`project_bind(project=NEW, current=OLD)`，先向用户确认返回的 `change`，再覆盖 `.rdm/project.json`。单次跨项目操作直接传 `project=OTHER`，不要改绑文件。
6. `.rdm/project.json` 不含密钥；是否提交由用户决定（希望每个开发者本地选择时加入 `.gitignore`）。

## 1. 开工三步：建立上下文

每次开始工作前按顺序调用：

1. `whoami` —— 确认身份、角色、未读信件数（unread_count）和我的未终态工作项数。
2. `mailbox_check(project=<绑定 KEY>)` —— 拉取当前绑定项目的信件与上下文（默认只拉未读；带 `since` 游标做增量拉取，把上一次返回的 `next_cursor` 传回去）。
3. `my_work_list(project=<绑定 KEY>)` —— 列出当前绑定项目分配给你的未终态工作项（也可用 `work_item_list` 参数 `assignee="me"` + `project=<KEY>`，`"me"` 是保留字，服务端解析为你的成员 id）。

**绑定后只处理该项目**：不要遍历 `whoami.projects`，不要查询、处理或建议处理其他项目的信件/工作项，除非用户明确要求。不要在没有上下文时直接改状态或发信。信箱（查信/回信/@mention/已读）的详细规范见 rdm-mailbox skill。

## 2. 认领工作项

1. 先 `work_item_get`（id 接受 `KEY-42` 显示 ID 或 ULID）确认 `assignee`、`status`、`meta.available_steps` 与 `meta.active_step`。
2. 未指派且该由你做：`work_item_assign` 把负责人设为自己（`member="me"`）。已有负责人时，只有负责人/参与人/manager/project_owner 能改派；不要争抢。
3. 认领后按当前状态的 direct 步骤推进（通常是 `TODO -> IN_PROGRESS`）。direct 步骤必须由该步骤的指定执行人执行；Owner/Manager 不能越权，需先变更负责人再操作。
4. 若认领时返回 `ALREADY_ASSIGNED`，说明被别人抢走/指派了——不要争，用 `mailbox_send` 联系其 accountable_human。
5. 需要评审/多人步骤时，负责人先维护 `reviewer`/参与人，再 `work_item_step(action="start", step_key=..., executors=[...])`。
## 3. 推进状态：direct 用 work_item_transition，命名步骤用 work_item_step

- 先 `work_item_get`，读 `meta.available_steps`（当前状态可执行的命名步骤、候选人、mode、note、gate）与 `meta.active_step`。
- **direct 步骤**（mode=direct）可由唯一候选执行人用 `work_item_transition` 或 `work_item_step(action="start")` 直接执行；`reason` 作为备注。
- **approval/task 步骤**不能直接流转；返回 `WORKFLOW_STEP_REQUIRED` 时改用 `work_item_step`：
  1. 负责人 `action="start"`，传 `step_key`、`row_version`、`executors`（候选唯一时可省略）。
  2. 被指派的执行人 `action="execute"`，传 `step_id`、`note_md`（note required 时必填）与可选 `attachment_ids`。
  3. 全部执行人完成后服务端自动流转；中途可 `cancel`/`reassign`（仅负责人），gate 阻塞时 `retry`。
  4. task 模式会为每名执行人创建一个子任务；执行人完成自己的子任务即可，不要直接 execute。
- 每次操作带最新 `row_version`/步骤 `row_version`；`CONFLICT_VERSION` 时重新 get。
- 活动步骤存在时普通 `work_item_transition` 返回 `WORKFLOW_STEP_IN_PROGRESS`；不要另起步骤。
- **gate 被拒**：读 `details.blocking_children` 与 `details.missing_fields`；先完成/取消子项、补齐字段，再重试同一操作。
## 4. 协作：一切走信箱

- 跨 human/agent 传递任何需要对方知道的信息，一律 `mailbox_send`，并用 `refs` 附上相关工作项 id。**不要靠 commit message、代码注释或口头约定传递工作信息。**
- 收件人 `to/cc` 可传成员 name/id 或 group 信箱名；发信前如不确定名字，先在项目上下文中确认，不要猜。
- 在工作项下发用 `comment_add`；评论里 `@成员名` 会自动给对方发一封站内信（找不到名字或重名时静默忽略）。
- 回复信件使用 `reply_to`，保持线程。

## 5. 完成工作

1. task 完成后先回填实际工时（`work_item_update` 改 `actual_work_hours` 等特型字段）。
2. 按工作流推进到 `TO_REVIEW`（direct 步骤）。
3. **停住。agent 不能作为 DONE 步骤的执行人**（服务端按身份类型判定，§17.70/81）：DONE 目标的候选执行人会过滤 agent。需要评审时，负责人维护 reviewer 并启动 `CODE_REVIEW`/任务式步骤，由 human 执行人收口；agent 可以执行非 DONE 步骤或完成自己的评审子任务。
4. story 在 TO_TEST、task 在 TO_REVIEW 后用 `mailbox_send` 通知 accountable_human 验收。issue 的 CLOSED_DONE 是 QA 关单，不受 DONE 身份限制。
5. Story/Issue/Epic 进入终态有 gate：所有直接子项必须先终态；issue 关闭还要求至少 1 个子任务。
## 6. 异常处理

- 一切错误都是结构化信封 `{"error": {"code", "message", "details"}}`：按 `message` 的中文指引行动，`details`（如 allowed_transitions、available_steps、blocking_children、missing_fields、current_version）给具体数据。
- `FORBIDDEN` / `WORKFLOW_STEP_FORBIDDEN`：你的身份无权做此事（步骤只能由负责人发起/改派，只能由被指派执行人执行；sprint 创建/启动/关闭仅 owner/manager）——用 mailbox_send 请求有权限的人协助，不要重试。
- `WORKFLOW_STEP_REQUIRED`：目标不是唯一 direct 步骤；按 `details.available_steps` 的 `key` 调用 `work_item_step`，不要硬转。
- `WORKFLOW_STEP_IN_PROGRESS`：已有活动步骤；继续 `execute`/`retry`，或由负责人 `cancel`/`reassign`，不要另起步骤。
- `WORKFLOW_STEP_NO_CANDIDATES` / `WORKFLOW_STEP_NOTE_REQUIRED`：先补齐 reviewer/参与人/执行人，或填写必填备注。
- `NOT_FOUND`：id 错或不属于当前项目；重新 `work_item_get` / 查列表确认，**不要猜 id**。
- **同一个错误连续出现两次**：停止重试，`mailbox_send` 给 accountable_human，附上错误原文与你尝试的操作。
## 7. 图片与附件

- 工作项描述、评论、Sprint 目标里的图片是 **project 级附件**，正文写成
  `![说明](/api/v1/attachments/<id>/download)`；不要内嵌 base64。
- `work_item_get` 的 `meta.attachments`、`comment_list` 每条评论的 `attachments`、
  `attachment_list(owner_type="project", project=KEY)` 都会返回附件元数据。
  其中 `state="temp"` 是编辑器草稿，`state="active"` 才是已保存内容。
- 每个附件元数据带 `fetch_url`（15 分钟有效的签名下载链接），可直接
  `curl -L "<fetch_url>" -o /tmp/image.png`，不需要额外 Bearer。
  若没有 `fetch_url`，用 PAT：`curl -H "Authorization: Bearer $RDM_TOKEN"
  http://127.0.0.1:8765<download_url> -o file`。不要猜附件 id。
- 上传/删除附件只能走 Web/OpenAPI：`POST /projects/<key>/attachments`
  （multipart，`owner_type=project` 或 `work_item`）；MCP 不传二进制。

## 8. 禁止事项

- 不要猜工作项/成员 id；先查询。
- 不要尝试绕过 `work_item_transition`/`work_item_step` 改状态。
- 不要执行未指派给自己的步骤；不要修改分配给他人的工作项状态。
- 不要作为 agent 执行 DONE 目标的步骤（服务端会过滤候选）。
- 不要重复 `mailbox_send` 同一内容；对同一事项用 reply_to 回信。
- 不要忽略 gate 阻塞去尝试其他转换路径——状态机没有"绕路"。
