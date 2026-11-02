# workflow.json5 配置手册（v4）

> 适用：`src/rdm/resources/workflow.json5`（随包发布的唯一工作流定义）。
> 相关实现：`src/rdm/domain/workflow/schema.py`、`engine.py`；运行时行为见
> `docs/architecture.md §5.3` 与 §17.88–96。

> 实际文件是 **JSON5**（`src/rdm/resources/workflow.json5`）。JSON5 支持 `//`、`/* */`
> 注释与尾逗号；字符串建议使用双引号。本文示例均为 JSON5；标注「节选」的片段只展示
> 相关层级，插入到对应位置即可。

## 目录

1. [文件位置与加载方式](#1-文件位置与加载方式)
2. [顶层结构](#2-顶层结构)
   - [2.1 命名工作流定义（workflow_defs + use）](#21-命名工作流定义workflow_defs--use)
3. [kind 字段](#3-kind-字段)
   - [3.1 状态触发器：parent_triggers / child_triggers](#31-状态触发器parent_triggers-与-child_triggersschema-v4)
4. [step 字段](#4-step-字段)
5. [gate 字段](#5-gate-字段)
6. [fields：reviewer / review_content / 自定义字段](#6-fieldsreviewer--review_content--自定义字段)
7. [执行人、人数与权限](#7-执行人人数与权限)
8. [三种 step mode](#8-三种-step-mode)
9. [任务子类型（subtypes）](#9-任务子类型subtypes)
10. [常见配置配方](#10-常见配置配方)
11. [校验、调试与排错](#11-校验调试与排错)
12. [已知限制](#12-已知限制)

---

## 1. 文件位置与加载方式

- 文件：`src/rdm/resources/workflow.json5`，随 Python 包发布。
- 启动时由 `rdm.domain.workflow.loader.load_spec()` 用 `pyjson5` 解析、Pydantic 校验并冻结；
  任何非法配置会让服务启动失败，而不是运行时才报错。
- 单例缓存：修改 JSON5 后必须重启 `rdm serve` 才生效，没有热重载。
- **没有项目级覆盖**：所有项目共用这一份定义。需要项目差异时，用子类型或不同 kind 表达。
- JSON5 语法要点：
  - 支持 `//` 行注释、`/* */` 块注释、尾逗号；
  - 字符串建议双引号（也接受单引号）；键建议加双引号；
  - 中英文标签直接写 UTF-8；
  - 语法检查：
    ```bash
    uv run python -c "import pyjson5,pathlib; pyjson5.loads(pathlib.Path('src/rdm/resources/workflow.json5').read_text())"
    ```
- 查看当前生效配置：
  - REST：`GET /api/v1/workflow?kind=task&task_type=code_review`
  - MCP：`workflow_get(kind="task", task_type="code_review")`
  - 详情：`work_item_get` 返回的 `meta.available_steps` / `meta.active_step`

---

## 2. 顶层结构

完整 JSON5 骨架（其余任务类型/kind 用注释省略）：

```json5
{
  "version": 3,

  // 任务类型目录：code -> 中文标签；子类型 key 必须出现在这里。
  "task_types": {
    "other": "其他",
    "frontend": "前端开发",
    "backend": "后端开发",
    "fullstack": "全栈开发",
    "code_review": "代码评审",
    "testing": "测试",
    "test_case_design": "测试用例设计",
    "docs": "文档编写",
    "ui_design": "UI设计",
    "product_design": "产品设计",
    "release": "系统发布",
    // ... 如需新增任务类型，在这里补 code: 标签
  },

  "kinds": {
    "task": {
      "label": "任务",
      "states": ["TODO", "IN_PROGRESS", "DONE"],
      "initial": "TODO",
      "terminal": ["DONE"],
      "steps": {
        "TODO": [{"key": "START", "name": "开始", "to": "IN_PROGRESS"}],
        "IN_PROGRESS": [{"key": "FINISH", "name": "完成", "to": "DONE"}],
        "DONE": []
      }
    },
    // ... 其余 kind（epic/story/issue/sprint）按同样结构声明
  }
}
```

- `version`：当前为 `3`。
- `task_types`：唯一标签来源；任务类型的合法值以它为准。后端仍接受 `qa → testing`、
  `ux_design → ui_design` 两个输入别名，但存储和输出使用规范值。
- `task_type_labels_en`（可选）：与 `task_types` 同 key 的英文标签表；缺省时英文界面
  回退中文标签。示例：`{"other": "Other", "frontend": "Frontend", …}`。
- `kinds`：至少一个；通常包含 `epic/story/issue/task/sprint`。
- `workflow_defs`（可选）：命名工作流定义，供 kind/subtype 用 `use` 引用，见 2.1。

### 2.1 命名工作流定义（workflow_defs + use）

当多种 kind 或 task subtype 需要**同一套状态机与步骤**时，不必逐条复制配置：
在顶层 `workflow_defs` 里定义一次，然后用 `use: "<name>"` 引用。

```json5
{
  "workflow_defs": {
    // 名称：小写字母开头，仅 a-z0-9_，最长 50 字符
    "dev_flow": {
      "states": ["TODO", "IN_PROGRESS", "TO_REVIEW", "DONE"],
      "initial": "TODO",
      "terminal": ["DONE"],
      "fields": {"reviewer": true, "review_content": true},
      "steps": {
        "TODO": [{"key": "START", "name": "开始", "to": "IN_PROGRESS"}],
        "IN_PROGRESS": [{"key": "SUBMIT", "name": "提交评审", "to": "TO_REVIEW"}],
        "TO_REVIEW": [
          {
            "key": "APPROVE",
            "name": "评审通过",
            "to": "DONE",
            "mode": "approval",
            "actors": ["reviewers"],
            "executors": {"min": 1, "max": 2}
          }
        ],
        "DONE": []
      }
    },
    "qa_flow": {
      "states": ["TODO", "TESTING", "DONE"],
      "initial": "TODO",
      "terminal": ["DONE"],
      "steps": {
        "TODO": [{"key": "START", "name": "开始", "to": "TESTING"}],
        "TESTING": [{"key": "PASS", "name": "通过", "to": "DONE"}],
        "DONE": []
      }
    }
  },
  "kinds": {
    "task": {
      "label": "任务",
      "use": "dev_flow",          // states/initial/terminal/steps/gates/fields 全部来自定义
      "subtypes": {
        "frontend": {"use": "dev_flow"},   // 前端/后端/全栈共用同一套流程
        "backend": {"use": "dev_flow"},
        "fullstack": {"use": "dev_flow"},
        "testing": {"use": "qa_flow"}      // 测试任务走另一套流程
      }
    }
  }
}
```

规则：

- 定义体与 kind 的图定义同构：`states/initial/terminal/steps` 必填，`gates/fields` 可选；
  还可以声明 `parent_triggers` / `child_triggers`（见 §3.1）。
- `use` 只能与 `label`、`label_en`、`gates`、`fields`、`parent_triggers`、`child_triggers`
  （kind 还可加 `subtypes`）同时出现；`gates`/`fields`/触发器写了就**整体覆盖**定义里的同名键，
  不按字段合并。
- 用 `use` 时不能再写 `states/initial/terminal/steps`——要改流程请改定义本身，
  或改用内联配置。错误信息会指明冲突键与引用的定义名。
- 定义内**不允许**再写 `use`（不做链式引用），避免解析顺序与循环引用问题。
- 引用不存在的定义、定义名不合法、定义体非法都会在加载/启动时报错，并带上
  `workflow_defs.<name>` 前缀。
- 引用在加载时即展开为普通图：REST/MCP 的 `GET /api/v1/workflow`、`workflow_get`、
  `meta.available_steps`、`rdm workflow validate` 看到的都是**解析后的**状态与步骤，
  不暴露 `use` 结构，因此前端无需感知。
- 顶层 `version` 会作为 `config_schema_version`、`revision` 作为 `config_version` 落到 `work_item_workflow_version`。
  - **修改配置结构**（字段形状、语法、语义）→ `version` 必须 +1，`revision` 也必须 +1。新增 `version` 时必须在 `src/rdm/domain/workflow/schema_versions/` 增加对应的 `vN.py` / `SchemaVn` 策略；旧策略保留，已固定的历史工作项仍按自己的 schema 版本读取。
  - **修改任意配置语义内容（含结构变更）** → `revision` 必须 +1；注释/排版除外。`config_version` 仅记录；是否产生新的 `work_item_workflow_version` 仍由生效定义是否相等决定。
  - `config_schema_version` 参与相等判断：`version` 变化时即使生效定义完全相同，也会强制生成新版本。
  - 两者都不参与运行时状态机判断，在途兼容由工作项固定的定义版本负责。
- 每个 `(kind, subtype)` **展开后**的生效定义会落库到 `work_item_workflow_version`。创建工作时项（及升级/启动的同步）会把当前定义与该 key 的最新版本比较：
  - 只改注释、空白或 JSON 对象键顺序**不会**产生新版本；
  - 改数组顺序（states/steps）、步骤/边、gate、字段或 `label`/`name` 等文案**会**产生新版本（`version` 自动 +1）；
  - 回退到历史内容也会生成一个新版本，不复用旧行。
- 旧工作项固定创建时的定义版本：之后改配置不会改变它的状态机、步骤 key、gate 或文案；新工作项使用当前定义。
- 升级时未固定的历史工作项会被绑定到**升级时的现行配置**（无法重建更早的定义）。如果本次升级同时删除了某个在用状态，需先迁移这些数据。
- task-mode 步骤的 `complete_on` 保存在父项固定定义中；子任务可能固定到另一版本，`rdm workflow validate` / `rdm doctor` 会对不一致给出提示。

### 2.2 新增配置结构版本

1. 改配置结构时递增 `workflow.json5` 的 `version`（同时递增 `revision`）。
2. 在 `src/rdm/domain/workflow/schema_versions/` 新增 `vN.py`，实现 `SchemaVn(DefinitionSchema)` 的 `_serialize` / `_deserialize`，并在包的 `__init__.py` 导入该模块。子类通过 `__init_subclass__` 自动注册；注册表与调用方不需要改。
3. **保留旧的 `SchemaVn` 实现**：已固定旧 schema 的工作项仍按自己的 `config_schema_version` 读取，不能为了“只支持最新版”而删除历史策略。
4. 如确需废弃某历史版本，必须先提供数据迁移（把工作项重新固定到新版本）并显式移除策略；未知版本会抛出 `UnsupportedWorkflowSchema`，doctor 报 FAIL。

---

## 3. kind 字段

节选：一个 kind 的字段结构。

```json5
{
  "kinds": {
    "task": {
      "label": "任务",
      "states": ["TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED"],
      "initial": "TODO",
      "terminal": ["DONE", "CANCELLED"],

      // 可选：开启 reviewer/review_content 与自定义字段
      "fields": {},

      // 可选：按目标状态的默认 gate
      "gates": {},

      // 必须为每个状态声明一条；空状态写 []
      "steps": {
        "TODO": [],
        "IN_PROGRESS": [],
        "BLOCKED": [],
        "DONE": [],
        "CANCELLED": []
      },

      // 可选：task 子类型工作流（可用 use 引用命名定义）
      "subtypes": {}
    }
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `label` | 否 | 展示名；缺省用 kind 名 |
| `label_en` | 否 | 英文展示名；`Accept-Language: en` 时使用，缺省回退 `label` |
| `states` | 是 | 状态全集；大写字符串，DB/API 原样存储 |
| `initial` | 是 | 初始状态，必须在 `states` 中 |
| `terminal` | 是 | 终态集合，必须在 `states` 中；可为空数组 |
| `steps` | 是 | 必须为**每个状态**声明一条（可为 `[]`） |
| `gates` | 否 | `{"目标状态": GateSpec}`，作为所有进入该状态步骤的默认 gate |
| `fields` | 否 | 开启 reviewer/review_content 与自定义字段 |
| `subtypes` | 否 | 子类型覆盖；目前用于 `task` |
| `parent_triggers` | 否 | 子项侧触发器：我变了 → 父项变；任意 kind/subtype 可用，见 3.1（v4 新增） |
| `child_triggers` | 否 | 父项侧触发器：直接子项变了 → 我变；可匹配不同 kind/subtype，见 3.1（v4 新增） |
| `use` | 否 | 引用 `workflow_defs` 中的命名定义；见 2.1 |

兼容输入：也可以用旧式 `"transitions": {"TODO": ["IN_PROGRESS"]}` 代替 `steps`。
加载时会转换为 `key=TO_<TARGET>`、`name=<TARGET>`、`mode=direct`、`actors=["assignee"]`
的步骤。同一 kind 不能同时声明 `steps` 和 `transitions`。

声明 `use` 时，上表标为必填的 `states/initial/terminal/steps` 由命名定义提供，
本层不能重复声明（见 2.1）。`parent_triggers` / `child_triggers` 属于可选语义，
命名定义里可以声明，kind/subtype 本地声明会整体覆盖；子类型显式写 `[]` 表示不继承。

### 3.1 状态触发器：parent_triggers 与 child_triggers（schema v4）

引擎支持两个方向，规则都来自工作项的**固定定义快照**（§17.120），并且**适用于任意
kind/subtype**（不只 task）：

| 键 | 声明位置 | 含义 |
|---|---|---|
| `parent_triggers` | 子项定义 | 本项变化时，按 `trigger` 命中事件、按 `when` 检查父项子项状态，执行 `parent` 动作 |
| `child_triggers` | 父项定义 | 直接子项变化时，按 `trigger` 命中事件、按 `when` 检查本项子项状态，执行 `self` 动作 |

一条规则由三部分组成：

```json5
{
  "trigger": { /* 触发事件：哪个子项发生了哪种状态变化（可选） */ },
  "when": { /* 触发时的当时状态：目标项的直接子项集合（可选） */ },
  "self": { "from": ["TODO"], "to": "IN_PROGRESS" }, // 动作（parent_triggers 用 parent）
  "on_error": "fail"                                  // 可选
}
```

- `trigger` 与 `when` 都是可选的，但**至少声明一个**。
- 省略 `trigger` 时，任一直接子项的状态变化都会触发评估。
- 省略 `when` 时，不做子项集合状态判断，只按 `trigger` 命中的事件执行动作。
- `trigger` 与 `when` 同时存在时是 AND：先命中变化事件，再检查当时状态。

#### trigger：触发事件

`from` / `to` 是**变化子项**的状态谓词，与 `when` 子句同形：

```json5
"trigger": {
  "kinds": ["task", "issue"],              // 变化子项的 kind
  "tasktypes": ["frontend", "backend"],    // 变化子项的 task 子类型；也接受 task_types
  "from": {
    "statuses": ["TODO"],                  // 变化前状态集合（任一）
    "start": true,                         // 变化前是否处于初始状态
    "terminal": false                      // 变化前是否终态
  },
  "to": {
    "statuses": ["DONE", "CLOSED_DONE"],   // 变化后状态集合（任一）
    "terminal": true                       // 变化后是否终态
  }
}
```

- `statuses` / `start` / `terminal` 之间是 AND；省略表示不限制。
- `start` / `terminal` 按**变化子项自己的固定定义**判断（§17.120），因此一条规则可以
  同时覆盖不同 kind/tasktypes 的不同状态名。
- 兼容简写：`from: ["TODO"]`、`to: "DONE"` 会自动归一化为 `statuses`。
- 跨 kind 只关心“进入终态”时可以写：
  ```json5
  "trigger": {
    "kinds": ["task", "issue"],
    "from": {"terminal": false},
    "to": {"terminal": true}
  }
  ```
- `tasktypes` 要求 `kinds` 为空或包含 `task`。

#### when：触发时的历史/当前状态

`when` 支持 `any` 和 `all`，各自是一个“子项选择器 + 当前状态谓词”对象：

```json5
"when": {
  "any": {
    "kinds": ["task"],
    "tasktypes": ["frontend"],   // 也接受 task_types
    "statuses": ["IN_PROGRESS", "IN_REVIEW"],
    "start": false,              // 是否处于该子项工作流的初始状态
    "terminal": false            // 是否终态
  },
  "all": {
    "kinds": ["task", "issue"],
    "terminal": true
  }
}
```

- `any`：按自己的选择器选出子项，**至少一个**满足 `statuses`/`start`/`terminal`。
- `all`：按自己的选择器选出子项，**所有**都满足。
- `any` 与 `all` 可同时出现，选择器各自独立，二者 AND；至少要声明一个。
- `statuses` / `start` / `terminal` 之间也是 AND；省略表示不限制。
- 某个量词选中的集合为空时，该量词视为**不满足**（不做空集真值）。
- `start` / `terminal` 按子项**自己的固定定义**判断（§17.120）。

```json5
{
  // 任一 task 子项当前 DONE → 触发
  "when": {"any": {"kinds": ["task"], "statuses": ["DONE"]}},
  "self": {"from": ["TO_TEST"], "to": "DONE"}
}
```

```json5
{
  // 所有 task 子项都终态 → 触发（issue 子项不参与）
  "when": {"all": {"kinds": ["task"], "terminal": true}},
  "self": {"from": ["TO_TEST"], "to": "DONE"}
}
```

#### child_triggers（推荐：聚合不同 kind/subtype 的子项）

```json5
{
  "kinds": {
    "story": {
      // ... states / steps ...
      "child_triggers": [
        {
          // 开发类子任务由 TODO -> IN_PROGRESS 时，若当时仍有开发子项在
          // IN_PROGRESS/IN_REVIEW，则需求 TODO -> IN_PROGRESS
          "trigger": {
            "kinds": ["task"],
            "tasktypes": ["frontend", "backend", "fullstack"],
            "from": ["TODO"],
            "to": "IN_PROGRESS"
          },
          "when": {
            "any": {
              "kinds": ["task"],
              "tasktypes": ["frontend", "backend", "fullstack"],
              "statuses": ["IN_PROGRESS", "IN_REVIEW"]
            }
          },
          "self": {"from": ["TODO"], "to": "IN_PROGRESS"}
        },
        {
          // 所有直接子项终态 → 需求 TO_TEST -> DONE
          "when": {"all": {"kinds": ["task", "issue"], "terminal": true}},
          "self": {"from": ["TO_TEST"], "to": "DONE"}
        }
      ]
    }
  }
}
```

规则列表之间是 OR；每条规则内部 `trigger`、`when`、目标项守卫之间是 AND。子句的
`kinds` 为空表示统计该层级所有直接子项。

#### 动作：self / parent

动作除了按目标状态 `to` 流转，也可以直接指定 **step key**：

```json5
{
  "trigger": {"kinds": ["task"], "to": "CANCELLED"},
  "self": {
    "from": ["TO_TEST"],
    "step": "PASS"        // 直接执行名为 PASS 的步骤
  }
}
```

```json5
{
  "self": {
    "from": ["TO_TEST"],
    "to": "DONE",
    "step": "PASS"        // 可选：同时指定，用于校验步骤目标确实是 DONE
  }
}
```

- `to` / `step` 至少写一个。
- `step` 使用 step **key**（`^[A-Z][A-Z0-9_]{1,49}$`），不是展示名。
- **只有 `mode=direct` 的步骤会自动执行**；approval/task 步骤会被跳过并记录 WARNING，
  避免绕过人工审批/子任务执行。
- 同时写 `to` 和 `step` 时，步骤的 `to` 必须与 `to` 一致，否则跳过并记录 WARNING。
- 未写 `step` 时，仍按当前状态到 `to` 的**唯一**步骤执行；同名目标有多个步骤时跳过。
- 动作仍受 `from` 守卫、gate、目标项活动步骤检查约束。

#### 错误处理：on_error

每条规则可选 `on_error`，默认 `"fail"`：

```json5
{
  "when": {"all": {"kinds": ["task", "issue"], "terminal": true}},
  "self": {"from": ["TO_TEST"], "to": "DONE"},
  "on_error": "ignore"   // fail（默认）| ignore
}
```

| 值 | 行为 |
|---|---|
| `fail`（默认） | 预期外异常（数据库/校验/通知等）向上抛出，**整个主操作回滚**；调用方收到错误 |
| `ignore` | 该规则包在 SAVEPOINT 中；预期外异常只记 ERROR 日志，回滚该规则的局部写入（父项状态、事件、站内通知、webhook outbox、SSE 回调），**主操作照常成功**；后续规则继续按回滚后的目标状态评估 |

注意：

- `on_error` 只影响**预期外异常**。条件不匹配、目标不可达/多个步骤、gate 不满足、
  目标项有活动步骤这些“正常不触发”的情况始终静默跳过，不记错误日志。
- `ignore` 的隔离粒度是**单条规则**；同一事件的其他规则不受影响。
- 日志 logger 为 `rdm.application.services.workitem_service`，包含子项 display id、
  父项 id 与目标状态。

#### parent_triggers（子项侧，适合专属规则）

```json5
{
  "kinds": {
    "issue": {   // 任意 kind 都可以，不限 task
      // ... states / steps ...
      "parent_triggers": [
        {
          // 本 issue 由 TO_FIX -> FIXING 时
          "trigger": {"kinds": ["issue"], "from": ["TO_FIX"], "to": "FIXING"},
          // 父项的直接子项中存在已离开初始状态的 issue
          "when": {"any": {"kinds": ["issue"], "start": false}},
          "parent": {"from": ["IN_PROGRESS"], "to": "TO_TEST"}
        }
      ]
    }
  }
}
```

执行规则（`WorkItemService._apply_parent_triggers`）：

1. 规则至少要声明 `trigger` 或 `when` 之一。`trigger` 存在时先匹配本次变化的子项
   事件（`kinds` / `tasktypes` / `from` / `to`）；省略 `trigger` 时任一直接子项状态
   变化都会触发评估。
2. `trigger` 与每个 `any`/`all` 子句的 `kinds` / `tasktypes` 必须是已知值；
   `tasktypes` 要求 `kinds` 为空或包含 `task`。`from`/`to`/`statuses` 是子项状态，
   不在加载期跨 kind 校验；`start`/`terminal` 按子项 pinned 定义在运行时判断。
3. `when` 存在时，每个子句先按自己的 `kinds`/`tasktypes` 选出直接子项；`any` =
   至少一个满足，`all` = 所有选中项都满足。`statuses`/`start`/`terminal` 之间 AND；
   选中集合为空时该子句不满足。`trigger` 与 `when` 之间也是 AND。
4. 目标项（`parent` 或 `self`）当前状态必须满足 `from`；省略 `from` 时只允许非终态，且不会重复进入目标状态。
5. 动作按 `step` 或 `to` 解析：
   - `step`：必须是当前状态可达的 step key，且 `mode=direct`；approval/task 步骤跳过并记 WARNING；
   - `to`：必须能从当前状态经**唯一**一步到达；同名目标有多个步骤时不自动选择，规则跳过。
   - 同时写 `to` + `step` 时二者目标必须一致，否则跳过并记 WARNING。
6. 自动流转仍走目标项自己的 gate（`required_fields`、`children_all_terminal` 等）；
   gate 不满足时跳过，不报错。目标项存在进行中的步骤时也跳过，避免与人工步骤冲突。
7. 自动流转写正常的 `work_item.status_changed` 事件（`payload.auto=true`），
   `reason` 记录触发的子项与前后状态。
8. **同步执行、同一事务**：触发器在子项状态变更的同一个 UoW 事务内执行，成功后才一起
   commit；不会异步延后，也不会出现“子项成功、父项稍后变”的中间态。
   - 预期内的不触发（条件不匹配、目标不可达/多个步骤、gate 不满足、目标项有活动步骤）
     静默跳过，子项操作照常成功；
   - 预期外的异常（数据库冲突、校验/写库错误等）按规则的 `on_error` 处理：`fail`
     向上抛出并回滚整个事务；`ignore` 只回滚该规则并记录 ERROR 日志，主操作继续；
   - 级联深度上限 10，超过后静默停止。

注意：生产 `workflow.json5` 目前是 `version: 4`、`revision: 13`，**没有声明任何规则**；
按实际场景配置后需递增 `revision`，并在合并前跑 `rdm workflow validate`。

---

## 4. step 字段

节选：`TO_REVIEW` 状态下的 Code Review 步骤。

```json5
{
  "steps": {
    "TO_REVIEW": [
      {
        "key": "CODE_REVIEW",
        "name": "Code Review",
        "to": "DONE",
        "mode": "approval",
        "actors": ["assignee", "reviewers"],
        "executors": {"min": 1, "max": 3},
        "note": "required",
        "gates": {
          "required_fields": ["review_content"]
        },
        "tasks": null
      }
    ]
  }
}
```

| 字段 | 默认 | 约束与说明 |
|---|---|---|
| `key` | 必填 | `^[A-Z][A-Z0-9_]{1,49}$`；在**同一 `from_state` 内唯一**（不同状态可复用 `CANCEL`）。API/UI/MCP 用它与 `step_id` 定位步骤 |
| `name` | 必填 | 展示名，如「Code Review」「打回修改」 |
| `name_en` | 否 | 英文展示名；`Accept-Language: en` 时使用，缺省回退 `name` |
| `to` | 必填 | 目标状态，必须在 `states` 中 |
| `mode` | `"direct"` | `"direct"` / `"approval"` / `"task"`，见 §8 |
| `actors` | `["assignee"]` | 执行人**类型**集合：`assignee`、`participants`、`managers`、`reviewers`、`project_members`；不可重复、不可为空 |
| `executors` | `{"min": 1, "max": 1}` | 指派人数范围；`"max": null` 表示不超过候选人数。实际被指派的人**全部**完成后才流转 |
| `note` | `"optional"` | `"optional"` / `"required"`；每个执行人各写一条备注。`mode="task"` 时禁止 `"required"` |
| `gates` | 继承 kind 级同目标 gate | 按字段覆盖 kind 默认；见 §5 |
| `tasks` | `null` | 仅 `mode="task"` 必填：`{"type", "title", "complete_on"}` |

`key` 的定位方式：

- 从当前状态开始时：`POST /work-items/{ref}/steps/{key}`。
- 已发起后：用 `active_step.id` 调 `/work-item-steps/{id}/execute|cancel|retry|reassign`。
- MCP：`work_item_step(action="start", step_key=...)` 或 `action="execute", step_id=...`。

---

## 5. gate 字段

节选：一个 GateSpec 对象。

```json5
{
  "children_all_terminal": true,
  "min_children": 1,
  "no_nonterminal_sprint_items": true,
  "required_fields": ["review_content", "test_case"]
}
```

| 字段 | 说明 |
|---|---|
| `children_all_terminal` | 所有直接子项都处于各自 kind 的终态；错误 details 带 `blocking_children` |
| `min_children` | 至少 N 个直接子项；`0` 表示显式取消父级默认约束 |
| `no_nonterminal_sprint_items` | Sprint 内所有工作项终态（Sprint 关闭用） |
| `required_fields` | 1-N 个字段必须非空；错误 details 带 `missing_fields` |

`required_fields` 可引用：

- master：`title`、`description_md`
- kind 特型：`acceptance_criteria_md`、`severity`、`environment`、`repro_steps_md`、
  `expected_behavior_md`、`actual_behavior_md`、`task_type`、`est_work_hours`、
  `actual_work_hours`、`code_branch`
- 已开启的内置字段：`reviewer`、`review_content`
- 已声明的自定义字段 key

非空判定：文本去空白后非空；数字非 `null`（`0` 算有值）；user/reviewer 列表非空。

**gate 合并规则（容易踩坑）**

1. kind 级 `gates[目标状态]` 是默认值。
2. step 级 `gates` 存在时**按字段覆盖**：step 显式写出的字段覆盖默认，其余沿用。
   - 例：kind 默认 `"DONE": {"children_all_terminal": true}`，step 写
     `"gates": {"required_fields": ["review_content"]}` → 两个条件同时生效。
3. 要取消某个默认布尔 gate，可显式写 `false`：
   `"gates": {"children_all_terminal": false}`。
4. 要取消默认的 `required_fields`，可写 `"required_fields": []`。
5. 要取消默认的 `min_children`，可写 `"min_children": 0`。
6. step 写成 `"gates": {}` 表示完全沿用 kind 默认。

---

## 6. fields：reviewer / review_content / 自定义字段

节选：`fields` 对象。

```json5
{
  "fields": {
    "reviewer": true,          // 0-N 人，可检索
    "review_content": true,    // Markdown，可检索
    "custom": [
      {"key": "test_case", "label": "测试用例", "type": "text"},
      {"key": "risk_score", "label": "风险分", "type": "number"},
      {"key": "observers", "label": "旁听人", "type": "user", "multiple": true},
      {"key": "owner", "label": "复核人", "type": "user", "multiple": false}
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `reviewer` | 内置评审人字段；开启后工作项可维护 0-N 人，可作 `"actors": ["reviewers"]` 的候选池，可用于 gate |
| `review_content` | 内置评审意见（Markdown）；开启后可用于 gate |
| `custom[].key` | `^[a-z][a-z0-9_]{0,49}$`；不可与 `title/description_md/reviewer/review_content` 冲突 |
| `custom[].label_en` | 否 | 英文标签；缺省回退 `label` |
| `custom[].type` | `text`（Markdown）、`number`、`user`（项目成员） |
| `custom[].multiple` | 仅 `type="user"` 可设；`true` 多选，`false` 单选 |

检索能力：

- `reviewer`：`GET /projects/{key}/work-items?reviewer=me|成员名|ULID`。
- `review_content`：列表 `q=` 同时匹配 title 与 review_content。
- 自定义字段：**不参与检索**，只在详情/编辑中读写。
- `reviewer`/`review_content` 是独立轻量字段，不天然绑定状态流转；步骤要使用 reviewer
  作为执行人时，负责人需先维护 reviewer，再在步骤里从其中选执行人（不回写）。

存储：`reviewer` 在 `work_item_reviewer` join 表，`review_content` 在
`work_item.review_content_md`，自定义字段在 `work_item.custom_fields`（DB 类型 JSON）。

---

## 7. 执行人、人数与权限

### 7.1 候选池

| actor source | 解析结果 |
|---|---|
| `assignee` | 当前负责人（1 人） |
| `participants` | participant 行 ∪ 负责人 |
| `managers` | 项目内 human 成员中 roles 含 `manager` 或 `project_owner` 的人 |
| `reviewers` | `reviewer` 字段的人 |
| `project_members` | 项目内全部启用成员（human 与随 manager 入项的 agent） |

- 只保留仍在本项目、启用的成员。
- `project_members` 是全体成员，因此包含负责人、参与人、评审人与 Owner/Manager，通常用于「任意成员都可执行」的审批类步骤；`mode="direct"` 要求唯一候选，配 `project_members` 时一般无法执行。
- 候选执行人不按目标状态过滤 agent（§17.102）：agent 只要是 `actors` 来源解析出的候选人，就可以作为 `DONE` 步骤的执行人；其 human manager 也可代操作（§17.101）。
- `reviewers` 为空且 `actors` 只有 `reviewers` 时，该步骤没有候选人，无法发起。

### 7.2 自动指定与人数

- `executors.min/max` 限制“实际指派几名执行人”，不是候选人数量。
- 自动指定：
  - 候选恰好 1 人且在范围内；或
  - `min == max == 候选人数`。
- 其他情况由负责人在发起时多选；UI 会显示候选人、范围与自动预选。
- 被指派的人**全部**完成后步骤才完成并自动流转。
- 改派后，被移出的执行人记为 `CANCELLED` 仅作审计，不参与完成判定；剩余执行人全部完成后即流转。
- `"max": null` 表示不设上限（不超过候选人数）。

### 7.3 权限

| 操作 | 谁可以做 |
|---|---|
| 发起 / 指派执行人 / 取消 / 重试 / 改派 | 当前负责人 |
| 执行 | 被指派且仍 PENDING 的执行人 |
| direct 步骤执行 | 解析出的唯一候选执行人 |
| 编辑工作项内容 | 负责人、参与人、manager、project_owner |
| 改派工作项负责人 | 负责人/参与人/manager/project_owner；未指派时任何项目成员可自领（`me`） |

Owner/Manager **不能越权执行**未指派给自己的步骤。接管方式：先变更负责人，再以负责人
身份改派/执行。

---

## 8. 三种 step mode

### 8.1 `direct`（默认）

```json5
{"key": "START", "name": "开始", "to": "IN_PROGRESS"}
```

- 必须 `"executors": {"min": 1, "max": 1}`，且运行时解析出的候选恰好 1 人。
- 由该唯一候选直接执行：`POST /work-items/{ref}/steps/{key}` 或 legacy
  `POST /work-items/{ref}/transition`。
- 也写一条 `COMPLETED` step 记录（审计与 UI 统一）。
- `"note": "required"` 时执行必须带备注；备注落为评论。
- 看板拖拽只对这类步骤开放（且 note 可选、无 gate）。

### 8.2 `approval`

```json5
{
  "key": "CODE_REVIEW",
  "name": "Code Review",
  "to": "DONE",
  "mode": "approval",
  "actors": ["assignee", "reviewers"],
  "executors": {"min": 1, "max": 3},
  "note": "required"
}
```

- 负责人 `POST /work-items/{ref}/steps/CODE_REVIEW {"row_version": ..., "executors": [...]?}`
  发起；候选唯一/固定时自动指定。
- 每个执行人 `POST /work-item-steps/{step_id}/execute {"note_md": ..., "attachment_ids": [...]?}`
  提交自己的备注；备注 required 时不能为空。
- 全部执行人 DONE 后自动完成步骤并流转父项。
- 部分完成时工作项保持原状态，详情 `meta.active_step.executors` 显示谁已完成/还差谁。
- 活动步骤存在时，普通 `/transition` 返回 `WORKFLOW_STEP_IN_PROGRESS`。

### 8.3 `task`（以子任务执行步骤）

```json5
{
  "key": "CODE_REVIEW_TASKS",
  "name": "Code Review（子任务）",
  "to": "DONE",
  "mode": "task",
  "actors": ["assignee", "reviewers"],
  "executors": {"min": 1, "max": 3},
  "tasks": {
    "type": "code_review",
    "title": "Code Review: {display_id} {title}",
    "complete_on": "DONE"
  }
}
```

- 发起时为**每名执行人**创建一个 `kind="task"`、`task_type=tasks.type` 的子任务，
  父项为当前工作项，负责人为执行人；`step_executor.task_id` 关联。
- 子任务进入 `complete_on` 状态时，该执行人被标记 DONE；全部执行人 DONE 后父项自动流转。
- `complete_on` 必须是该 task type 有效工作流的**终态**；默认 `"DONE"`。
- `mode="task"` 禁止 `"note": "required"`；备注由子任务自身的评论/流转备注承担。
- 父 kind 必须能挂 task 子项：`epic`、`story`、`issue`、`task`；`sprint` 配置 task 步骤会在
  加载时报错。
- 取消步骤会级联取消未完成的子任务；被活动步骤引用的子任务禁止删除/改父/改 task_type。

`title` 支持占位符：`{display_id}`、`{title}`、`{name}`、`{executor}`。

---

## 9. 任务子类型（subtypes）

节选：插入到 `kinds.task.subtypes` 下。

```json5
{
  "subtypes": {
    "code_review": {
      "label": "代码评审",
      "label_en": "Code Review",
      "states": ["TODO", "IN_PROGRESS", "DONE", "CANCELLED"],
      "initial": "TODO",
      "terminal": ["DONE", "CANCELLED"],
      "fields": {
        "reviewer": false,
        "review_content": false,
        "custom": [
          {"key": "review_scope", "label": "评审范围", "type": "text"}
        ]
      },
      "steps": {
        "TODO": [
          {"key": "START", "name": "开始评审", "to": "IN_PROGRESS"},
          {"key": "CANCEL", "name": "取消", "to": "CANCELLED"}
        ],
        "IN_PROGRESS": [
          {"key": "COMPLETE", "name": "完成", "to": "DONE"},
          {"key": "CANCEL", "name": "取消", "to": "CANCELLED"}
        ],
        "DONE": [],
        "CANCELLED": []
      }
    }
  }
}
```

合并规则：

- **声明了 `states`**：必须同时声明 `initial`、`terminal`，以及覆盖**全部**状态的
  `steps`；不与父级步骤合并。用于完全不同的状态图（如上面的 code_review）。
- **未声明 `states`**：继承父级 `states/initial/terminal`；`steps` 按 `from_state`
  合并——同 key 覆盖、新 key 追加、`"SOME_STATE": []` 清空该状态。未声明 `states` 时
  不能单独提供 `initial`/`terminal`。
- `fields`：`reviewer/review_content` 显式声明时覆盖父级；`custom` 按 key 合并。
- `gates`：子类型声明了就整体替换父级 `gates`，不按字段合并。
- `label`：子类型优先，否则父级。
- 子类型 key 必须在 `task_types` 中。
- `task_type` 创建后不可修改。
- 子类型也可以 `use` 一个命名定义（见 2.1）；此时视同声明了该定义的
  `states/initial/terminal/steps`，`gates/fields` 可整体覆盖，其余合并规则同上。

解析：`(kind, task_type)` → 有子类型用子类型，否则用 base kind。API/引擎在创建、流转、
列表终态判断、步骤候选都会使用解析后的有效工作流。

---

## 10. 常见配置配方

### 10.1 仅负责人可流转的简单步骤

节选：插入到某个 kind 的 `steps` 下。

```json5
{
  "steps": {
    "TODO": [
      {"key": "START", "name": "开始", "to": "IN_PROGRESS"}
    ],
    "IN_PROGRESS": [
      {"key": "FINISH", "name": "完成", "to": "DONE"}
    ]
  }
}
```

### 10.2 Code Review：多人审批 + 必填评审意见

节选：插入到某个 kind 的 `fields` / `steps` 下。

```json5
{
  "fields": {
    "reviewer": true,
    "review_content": true
  },
  "steps": {
    "TO_REVIEW": [
      {
        "key": "CODE_REVIEW",
        "name": "Code Review",
        "to": "DONE",
        "mode": "approval",
        "actors": ["assignee", "reviewers"],
        "executors": {"min": 1, "max": 3},
        "note": "required",
        "gates": {"required_fields": ["review_content"]}
      }
    ]
  }
}
```

使用：负责人先维护 `reviewer`，再发起步骤选 1-3 名执行人；每人提交备注；全部完成后
自动 DONE。打包定义的开发流程（`dev_standard`）当前关闭了 reviewer/review_content，
改用 `actors: ["assignee", "project_members"]`，即从全体项目成员中选执行人。

### 10.3 Code Review：每人一个评审子任务

节选：插入到某个 kind 的 `steps` 下。

```json5
{
  "steps": {
    "TO_REVIEW": [
      {
        "key": "CODE_REVIEW_TASKS",
        "name": "Code Review（子任务）",
        "to": "DONE",
        "mode": "task",
        "actors": ["assignee", "reviewers"],
        "executors": {"min": 1, "max": 3},
        "tasks": {
          "type": "code_review",
          "title": "Code Review: {display_id} {title}",
          "complete_on": "DONE"
        }
      }
    ]
  }
}
```

需要同时定义 `code_review` 子类型（或至少确保 `code_review` 的继承工作流不会递归创建
同类型 task 步骤）。

### 10.4 只有 manager/project_owner 能执行的步骤

节选：一个 step 对象。

```json5
{
  "key": "APPROVE",
  "name": "管理审批",
  "to": "DONE",
  "mode": "approval",
  "actors": ["managers"],
  "executors": {"min": 1, "max": 2},
  "note": "required"
}
```

若项目有多名 manager，负责人需要从中指定执行人；若只有 1 名，会自动指定。

### 10.5 字段门禁：填了测试用例才能 DONE

节选：插入到某个 kind 的 `fields` / `steps` 下。

```json5
{
  "fields": {
    "custom": [
      {"key": "test_case", "label": "测试用例", "type": "text"}
    ]
  },
  "steps": {
    "TO_TEST": [
      {
        "key": "PASS",
        "name": "验收通过",
        "to": "DONE",
        "gates": {"required_fields": ["test_case"]}
      }
    ]
  }
}
```

### 10.6 Sprint 关闭门禁

节选：插入到 `kinds` 下。

```json5
{
  "sprint": {
    "states": ["PLANNED", "ACTIVE", "CLOSED"],
    "initial": "PLANNED",
    "terminal": ["CLOSED"],
    "steps": {
      "PLANNED": [{"key": "START_SPRINT", "name": "启动 Sprint", "to": "ACTIVE"}],
      "ACTIVE": [{"key": "CLOSE_SPRINT", "name": "关闭 Sprint", "to": "CLOSED"}],
      "CLOSED": []
    },
    "gates": {
      "CLOSED": {"no_nonterminal_sprint_items": true}
    }
  }
}
```

Sprint 的步骤只用于声明合法性/gate；`SprintService` 不产生 step 记录，权限仍是
owner/manager 的 sprint 规则。

### 10.7 子项变更触发父项（RDM-71 示例，schema v4）

目标（对应 RDM-71 的示例，并覆盖 task/issue 混合子项）：

- 需求下开发类子任务当前处于 `IN_PROGRESS` 时，需求 `TODO → IN_PROGRESS`；
- 开发任务的 code_review 子任务当前处于 `DONE` 时，开发任务若在 `TO_REVIEW`，自动 `TO_REVIEW → DONE`；不在则不动作；
- 需求非终态、且所有直接子项（**task 或 issue 均可**）都已终态时，需求自动进入 `DONE`；
- 级联：子项 → 父任务 → 父需求。

注意：`trigger` 匹配**本次变化的子项事件**；`when` 判定**触发时的当前状态**。多数规则
可以只写 `trigger` 或只写 `when`；两者同时存在时先命中事件，再检查集合状态。

聚合规则写在**父项**定义上（`child_triggers`），一条规则即可同时匹配不同 kind：

```json5
{
  "workflow_defs": {
    "dev_standard": {
      // ...原有 states / initial / terminal / steps / gates / fields...

      "child_triggers": [
        // 规则 2：自己的 code_review 子任务当前 DONE → 自己 TO_REVIEW → DONE。
        {
          "trigger": {"kinds": ["task"], "tasktypes": ["code_review"], "to": "DONE"},
          "when": {
            "any": {"kinds": ["task"], "tasktypes": ["code_review"], "statuses": ["DONE"]}
          },
          "self": {"from": ["TO_REVIEW"], "to": "DONE"}
        }
      ]
    }
  },

  "kinds": {
    "story": {
      // ...原有 states / steps / gates / fields...

      "child_triggers": [
        // 规则 1：开发类子任务当前 IN_PROGRESS → 需求开始。
        {
          "trigger": {
            "kinds": ["task"],
            "tasktypes": ["frontend", "backend", "fullstack"],
            "from": ["TODO"],
            "to": "IN_PROGRESS"
          },
          "when": {
            "any": {
              "kinds": ["task"],
              "tasktypes": ["frontend", "backend", "fullstack"],
              "statuses": ["IN_PROGRESS"]
            }
          },
          "self": {"from": ["TODO"], "to": "IN_PROGRESS"}
        },
        // 规则 3：task 与 issue 子项混用；所有选中子项终态 → 需求 DONE。
        {
          "when": {"all": {"kinds": ["task", "issue"], "terminal": true}},
          "self": {"from": ["TO_TEST"], "to": "DONE"}
        }
      ]
    },

    "task": {
      "use": "task_standard",
      "subtypes": {
        "frontend": {"label": "前端开发", "use": "dev_standard"},
        "backend": {"label": "后端开发", "use": "dev_standard"},
        "fullstack": {"label": "全栈开发", "use": "dev_standard"},
        "testing": {"label": "测试", "use": "qa_standard"}
      }
    }
  }
}
```

如果规则只针对某一种子项、且不想把它放在父项定义里，也可以继续用子项侧的
`parent_triggers`；它的 `when` 同样是对**父项直接子项集合**的量词：

```json5
{
  "kinds": {
    "issue": {
      "parent_triggers": [
        {
          // 本 issue 由 TO_FIX -> FIXING；父项子项中存在 DONE 的 task
          "trigger": {"kinds": ["issue"], "from": ["TO_FIX"], "to": "FIXING"},
          "when": {"any": {"kinds": ["task"], "statuses": ["DONE"]}},
          "parent": {"from": ["IN_PROGRESS"], "to": "TO_TEST"}
        }
      ]
    }
  }
}
```

放置与生效说明：

1. **规则作用域**：`story.child_triggers` 只对直接父项是 story 的关系生效；
   `dev_standard.child_triggers` 只对使用该定义的父任务生效。子句的 `kinds` 为空表示统计所有子项 kind。
2. **混合 kind**：聚合规则使用 `when.all.kinds: ["task", "issue"]`（或省略 `kinds`）即可覆盖
   需求同时挂 task 和 issue 子项的情况，不需要在每个子项定义里重复声明。
3. **目标必须唯一可达**：自动流转不会在多条同名目标步骤中挑选。例如 `TO_REVIEW → DONE`
   必须只有一条步骤；如果同时启用 `CODE_REVIEW` 和 `CODE_REVIEW_TASKS`，规则 2 会被跳过。
   生产 `dev_standard` 当前只有 `CODE_REVIEW` 一条，可直接使用。
4. **gate 仍然生效**：父项 DONE 的 `children_all_terminal`、步骤 `required_fields` 不满足时，
   规则跳过而不是强行流转；父项有进行中步骤时也跳过。
5. **父项状态限制**：规则 3 显式写了 `self.from: ["TO_TEST"]`；生产 story 的 DONE
   只能从 `TO_TEST` 到达。省略 `from` 时由父项自己的步骤决定可达性，不可达则跳过。
6. **既有工作项不会自动获得新规则**：每个工作项固定创建时的定义快照（§17.120），
   规则只对**改配置后新建**的工作项生效；在途工作项仍按旧快照运行。
7. 改完必须递增 `revision`（当前 13）、重启服务，并跑 `rdm workflow validate`。

可直接运行的契约示例见 `tests/integration/test_parent_triggers.py`（父项侧混合
task+issue 聚合、kind 过滤、两级级联与“状态不匹配则不动作”）；字段/校验单测见
`tests/unit/test_workflow_parent_triggers.py`。

---

## 11. 校验、调试与排错

### 11.1 本地校验

```bash
# 加载并打印（任何 schema 错误会在这里抛出）
uv run python -c "from rdm.domain.workflow.loader import load_spec; s=load_spec(); print(s.version, list(s.kinds))"

# 引擎解析某个 kind/task_type
uv run python -c "
from rdm.domain.workflow.loader import load_engine
e=load_engine(); w=e.resolve('task','code_review')
print(w.states, w.initial, w.terminal)
for st in w.states:
    print(st, [(x.key,x.mode,x.to) for x in w.steps_from(st)])
"

# 单元测试
uv run pytest -q tests/unit/test_workflow_v3.py tests/unit/test_workflow_engine.py
```

导出严格 JSON（给 `jq`、JSON Schema、其他语言使用）：

```bash
uv run python -c "import json,pyjson5; from rdm.domain.workflow.loader import load_spec_text; print(json.dumps(pyjson5.loads(load_spec_text()), ensure_ascii=False, indent=2))"
```

### 11.2 启动后检查

- `GET /api/v1/workflow` 或 MCP `workflow_get` 看 `steps/fields/subtypes/task_types`。
- `GET /api/v1/work-items/{ref}` 看 `meta.available_steps`（候选人、mode、note、gate、auto_executors）。
- 发起后看 `meta.active_step`（执行人进度、备注、子任务、gate_details）。
- 历史：`GET /api/v1/work-items/{ref}/history` 含 `step_*` 动作。

### 11.3 常见报错

| 报错 | 原因 | 处理 |
|---|---|---|
| `workflow must define at least one kind` | `kinds` 为空 | 至少一个 kind |
| `steps must define an entry for every state` | 漏了某个状态 | 每个状态都写，空状态写 `[]` |
| `step ... targets unknown state` | `to` 不在 `states` | 改为合法状态 |
| `duplicate step key` | 同一 from_state 内 key 重复 | 换 key；不同状态可复用 |
| `direct mode requires executors {min:1,max:1}` | direct 配了多人 | 多人请用 `"mode": "approval"` |
| `task mode requires tasks` / `cannot require a step note` | task 配置不完整 | 补 `tasks`；`note` 不能 `"required"` |
| `complete_on ... is not terminal` | 完成条件不是子类型终态 | 改成该 task type 的终态 |
| `unknown task type` | `tasks.type` 不在 `task_types` | 补目录或改 type |
| `required field ... is not enabled or declared` | gate 引用了未开启/未声明字段 | 开 `fields` 或改 gate |
| `task steps require a parent kind that can contain tasks` | 在 sprint 配 task 步骤 | 改用 epic/story/issue/task |
| `workflow resolution cycle` | task 步骤创建同类型 task 导致递归 | 给该类型定义独立子类型或换 type |
| `declaring states must declare steps for every state` | 子类型声明了 states 但 steps 不全 | 补齐或删掉 `states` 走继承 |
| `unknown workflow_defs reference '…'` | `use` 指向不存在的定义 | 在 `workflow_defs` 补定义或改引用名 |
| `cannot declare ... alongside use` | `use` 与内联 `states/…/steps` 同时出现 | 二选一：改定义本身或改成内联配置 |
| `definitions cannot reference other definitions` | 定义内又写了 `use` | 把公共部分合并进同一份定义 |
| `workflow_defs.<name> is invalid: …` | 定义体不合法 | 按冒号后的具体错误修正定义 |

---

## 12. 已知限制

- 单一内置 `workflow.json5`，无项目级覆盖；改动需重启服务。
- 自定义字段定义只在 JSON5，不提供 Web 字段设计器。
- 自定义字段不参与列表检索；reviewer/review_content 可检索。
- `mode="task"` 不能要求步骤备注；备注由子任务承担。
- 不做步骤级“拒绝/退回”审批语义；取消 + 重新发起即可。
- 步骤事件暂不进入 webhook 白名单；通知能力后续实现。
- 运行中的步骤会快照 edge 配置（mode/note/tasks/gates 等）；gate 最终校验仍以当前加载的
  engine 为准，因此跨版本修改 `workflow.json5` 时建议先取消在途步骤再发布。
