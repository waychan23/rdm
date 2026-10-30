# web-next e2e（Playwright，重点覆盖工作流引擎）

浏览器端到端测试：启动真实的 `rdm serve`（临时 data dir + 随机端口），
用真实 OAuth 登录与真实 REST 写入准备数据，再在 **构建后的 SPA** 上操作
`/projects/:key/items/:id` 与看板，断言界面与数据库状态。

与仓库根 `e2e/` 的区别：`e2e/` 用 `claude -p` / `opencode run` 验收 agent+MCP
场景；本目录只测 Web 工作流交互，不依赖任何 LLM。

## 前置

- `uv sync`（global setup 用 `uv run rdm serve`）
- `pnpm -C web-next install`
- Chromium：`pnpm -C web-next exec playwright install chromium`
  （`@playwright/test` 固定 1.58.0，与本机已缓存的 Chromium 版本一致）
- 首次或改动前端后无需手工 build：`pnpm e2e` 会先 `pnpm build`，
  把产物写入 `src/rdm/resources/web-next-dist/` 再启动服务。

## 运行

```bash
pnpm -C web-next e2e                 # build + 全部 spec
pnpm -C web-next e2e:only            # 复用现有 dist，只跑 Playwright
pnpm -C web-next e2e:headed          # 有头模式观察交互
pnpm -C web-next exec playwright test 05-task-mode   # 按文件名过滤
pnpm -C web-next exec playwright test --repeat-each=2 # 稳定性回归
```

- 串行执行（`workers: 1`）。大多数 spec 共用临时项目 `WFE2E`，每个 spec 用唯一标题创建
  自己的工作项、互不清理；涉及分页/滚动/列表快照的 spec（如 10）会自建隔离项目，
  避免其他用例积累的行影响断言。
- 失败时 `e2e/.results/` 保留 trace / screenshot / video；
  `pnpm -C web-next exec playwright show-trace <trace.zip>` 可回放。
- 服务日志：`e2e/.auth/server.log`。`e2e/.auth/` 同时存放本次运行的
  浏览器 storageState（含临时 token），已 gitignore。

## 结构

```
e2e/
  global-setup.ts     # 启服务、owner recovery、建项目/用户、生成 storageState
  support/
    api.ts            # OAuth 登录 + 确定性 REST 造数（建项、直接步骤推到前置状态）
    context.ts        # global setup 与 spec 之间的运行上下文
    fixtures.ts       # app / api / asUser（多身份浏览器会话）/ 默认 owner page
    ui.ts             # testid 级交互封装（步骤对话框、执行人选择、拖拽）
  specs/
    01-login.spec.ts
    02-direct-step.spec.ts
    03-approval-step.spec.ts
    04-gate-blocked-retry.spec.ts
    05-task-mode-subtasks.spec.ts
    06-cancel-step.spec.ts
    07-subtype-workflow.spec.ts
    08-board-drag.spec.ts
    09-reassign-step.spec.ts
    10-dismiss-drawer.spec.ts
```

- **认证**：global setup 走完整 OAuth（`/authorize` → login ticket →
  `/api/v1/auth/login` → `/token`，PKCE + scope=web），把 access/refresh token
  写进每个身份的 `storageState`。`01-login` 额外用真实浏览器表单走一遍登录，
  其余 spec 直接注入 token 以节省时间。
- **造数**：`Api` 用各身份 token 调 REST。`createItem({status: ...})` 会沿
  direct 步骤图把工作项推到 `TO_REVIEW` 等前置状态；审批/执行/取消/拖拽等
  被测动作一律通过 UI 完成。
- **多身份**：`asUser("alice")` 打开独立浏览器上下文，用于验证「只有被指派的
  执行人能执行」「未指派的 reviewer 看不到执行按钮」等权限规则。

## 覆盖矩阵（工作流引擎）

| Spec | 覆盖的引擎规则 |
|---|---|
| 01-login | 无 session cookie 的 OAuth 登录、callback 换 token、进入应用 |
| 02-direct-step | 命名 `direct` 步骤、完成记录、历史 `step_completed` |
| 03-approval-step | `approval` 步骤、多人执行人、部分完成保持状态、全部完成才流转、非执行人不可执行 |
| 04-gate-blocked-retry | `required_fields` 启动预检、完成后 gate → `BLOCKED`、补齐字段后 `retry` 成功 |
| 05-task-mode-subtasks | `task` 步骤为每个执行人建子任务、子任务 `complete_on` 回写父项、父项 gate 自动流转 |
| 06-cancel-step | 取消活动步骤、工作项保持原状态、可重新发起、历史 `step_cancelled` |
| 07-subtype-workflow | `task_type=code_review` 子类型状态图、子类型字段/自定义字段、看板状态并集、字段就地编辑持久化 |
| 08-board-drag | 看板只允许「单一步骤 + direct + 备注可选 + 无 gate」的拖拽；审批步骤拒绝并提示进详情 |
| 09-reassign-step | 只有负责人可改派、PENDING 才可改派、被移出的执行人失去执行权、新执行人可完成步骤 |
| 10-dismiss-drawer | 点击详情背板空白处关闭面板；列表行等交互元素仍可切换工作项、不误关闭；开关面板不出现列表/看板 loading 闪烁，关闭后恢复列表滚动位置 |

## 新增 spec

```ts
import { expect, test } from "../support/fixtures";
import { openItem, stepButton } from "../support/ui";

test("...", async ({ api, app, asUser }) => {
  const item = await api.createItem({
    kind: "task",
    title: `case-${Date.now()}`,
    assignee: "alice",
    status: "TO_REVIEW", // 需要时用 direct 步骤推到前置状态
  });
  const page = await asUser("alice");
  await openItem(page, app, item);
  // 只通过 UI 触发被测行为
});
```

- 断言优先用 `data-testid`（页面已有约定），不要依赖样式或文本排序。
- 造数只做前置条件；不要在 setup 里直接调用被测的 step/transition 接口，
  否则 UI 规则（按钮可用性、gate 提示）就失去覆盖。
- 需要新增稳定定位时，优先在组件上加 `testId`，而不是用 CSS 选择器。
