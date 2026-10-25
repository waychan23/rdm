---
name: rdm-mailbox
description: rd-manager（rdm）站内信箱使用规范。当需要通过 rdm MCP 工具拉取信件、回信、@成员、标记已读或与其他 human/agent 异步协作时使用。
---

# rdm 站内信箱规范

信箱是 human 与 agent 之间**唯一的异步协作通道**。你通过 `mailbox_check` / `mailbox_send` /
`mailbox_mark_read` 三个工具使用它；硬规则在服务端，本规范讲时机与姿势。

## 1. 开工先查信

每次开工按顺序：`whoami` → `mailbox_check`（默认只拉未读）→ 再看自己的任务
（`my_work_list` 或 `work_item_list` assignee="me"）。出错被打回时也先查信，负责人的说明通常在信里。

- 增量拉取：把上一次响应的 `next_cursor` 作为 `since` 传回；`next_cursor` 为 null 表示没有更多。
- 信件条目里的 `delivery_id` 是**你这一份投递**的 id；标记已读传它，不要传 message_id。
- 处理完一批信件后调 `mailbox_mark_read`（delivery_ids 列表），未处理的不要标已读。
- 不要高频轮询：开工、转状态间隙、等待回复时检查即可。

## 2. 发信与回信

- `mailbox_send`：`to`/`cc` 传成员 name/id 或 group 信箱名；`refs` 附相关工作项
  （`KEY-42` 或 ULID），让对方一键定位上下文。
- 同一事项的后续沟通用回信链路（带 reply_to），不要新发标题相近的信。
- **不要重复发送**同一内容；对方没立刻回不是重发理由（不保证实时，转做别的任务）。
- 一条信说清：发生了什么、需要对方做什么、关联哪个工作项。

## 3. @mention 与评论

- 在工作项评论里 `@成员名`（精确匹配项目内唯一名）会给对方发一封站内信，
  refs 自动指向该工作项；用 `comment_add` 发评论，不要用评论推动状态。
- 找不到或重名的 @mention 会被静默忽略，并出现在响应的
  `meta.unresolved_mentions` 里——看到后先 `member_list` 核对名字，必要时在评论里补正确的 @，
  但不要原样重发整条评论。

## 4. 协作惯例

- 需要别的 agent/human 做事（评审、联调、回答问题）：发信并在对应工作项留评论，
  然后继续做不依赖对方的任务；不要空等。
- 完成被交付的事项后，给发件人回信说明结果（必要时附 refs 与状态）。
- group 信箱用于广播给一组人；点对点协作不要用 group。
- 信件是审计记录的一部分：事实、id、display_id 写准确，不要猜测名字或编号，
  先 `member_list` / `work_item_list` 查。
