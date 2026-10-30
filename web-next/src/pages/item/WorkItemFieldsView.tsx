import { Stack, Text } from "@atlaskit/primitives/compiled";

import TextButton from "../../components/TextButton";
import type { MarkdownImageClick } from "../../components/MarkdownText";
import type { WorkItem } from "../../types";
import { SEVERITY_OPTIONS } from "../../workitems/constants";
import {
  InlineChoiceField,
  InlineMarkdownField,
  InlineTextField,
} from "./InlineFields";

const TASK_TYPES: Record<string, string> = {
  product_design: "产品设计",
  ui_design: "UI设计",
  ux_design: "UI设计",
  frontend: "前端开发",
  backend: "后端开发",
  fullstack: "全栈开发",
  code_review: "代码评审",
  testing: "测试",
  qa: "测试",
  test_case_design: "测试用例设计",
  release: "系统发布",
  docs: "文档编写",
  other: "其他",
};

function Empty() {
  return (
    <Text size="small" color="color.text.subtlest">
      未填写
    </Text>
  );
}

/** Blank text clears the field instead of storing whitespace. */
function blankToNull(value: string): string | null {
  return value.trim() ? value : null;
}

const hoursText = (value: string) => (value.trim() ? `${value}h` : "—");

interface Props {
  item: WorkItem;
  projectKey: string;
  canEdit: boolean;
  onPatch: (payload: Record<string, unknown>) => Promise<boolean>;
  onOpenItem: (id: string) => void;
  onImageClick: (image: MarkdownImageClick) => void;
}

/**
 * Kind-specific fields. Each value edits in place and PATCHes only its own
 * top-level key (flat schema, see docs/web-next-ui.md §6.3).
 */
export default function WorkItemFieldsView({
  item,
  projectKey,
  canEdit,
  onPatch,
  onOpenItem,
  onImageClick,
}: Props) {
  const fields = (item.fields ?? {}) as Record<string, unknown>;
  if (item.kind === "epic" || Object.keys(fields).length === 0) {
    return (
      <Text size="small" color="color.text.subtlest">
        该类型没有额外字段
      </Text>
    );
  }

  if (item.kind === "story") {
    return (
      <InlineMarkdownField
        testId="item-acceptance"
        label="验收标准"
        value={fields.acceptance_criteria_md as string | undefined}
        canEdit={canEdit}
        projectKey={projectKey}
        emptyText="未填写"
        placeholder="填写验收标准（支持 Markdown）"
        minimumRows={3}
        editLabel="编辑验收标准"
        onImageClick={onImageClick}
        onSave={(next) => onPatch({ acceptance_criteria_md: blankToNull(next) })}
      />
    );
  }

  if (item.kind === "issue") {
    const sourceStoryId = fields.source_story_id as string | undefined;
    return (
      <Stack space="space.150">
        <InlineChoiceField
          testId="item-severity"
          label="严重度"
          value={String(fields.severity ?? "major")}
          options={SEVERITY_OPTIONS}
          canEdit={canEdit}
          editLabel="编辑严重度"
          onSave={(next) => onPatch({ severity: next })}
        />
        <InlineTextField
          testId="item-environment"
          label="环境"
          value={String(fields.environment ?? "")}
          canEdit={canEdit}
          emptyText="未填写"
          editLabel="编辑环境"
          onSave={(next) => onPatch({ environment: blankToNull(next) })}
        />
        <div className="rdm-inline-field" data-testid="item-source-story">
          <div className="rdm-item-section-label">来源 story</div>
          {sourceStoryId ? (
            <TextButton onClick={() => onOpenItem(sourceStoryId)}>
              {sourceStoryId}
            </TextButton>
          ) : (
            <Empty />
          )}
        </div>
        {(
          [
            ["repro_steps_md", "复现步骤"],
            ["expected_behavior_md", "期望行为"],
            ["actual_behavior_md", "实际行为"],
          ] as const
        ).map(([key, label]) => (
          <InlineMarkdownField
            key={key}
            testId={`item-${key}`}
            label={label}
            value={fields[key] as string | undefined}
            canEdit={canEdit}
            projectKey={projectKey}
            emptyText="未填写"
            placeholder={`填写${label}（支持 Markdown）`}
            minimumRows={3}
            editLabel={`编辑${label}`}
            onImageClick={onImageClick}
            onSave={(next) => onPatch({ [key]: blankToNull(next) })}
          />
        ))}
      </Stack>
    );
  }

  return (
    <Stack space="space.150">
      <div className="rdm-inline-field" data-testid="item-task-type">
        <div className="rdm-item-section-label">任务类型</div>
        <Text size="small">
          {TASK_TYPES[String(fields.task_type ?? "other")] ?? String(fields.task_type ?? "—")}
        </Text>
      </div>
      <InlineTextField
        testId="item-est-work-hours"
        label="预估工时（小时）"
        value={fields.est_work_hours === null || fields.est_work_hours === undefined
          ? ""
          : String(fields.est_work_hours)}
        canEdit={canEdit}
        emptyText="—"
        inputType="number"
        editLabel="编辑预估工时"
        renderView={hoursText}
        onSave={(next) =>
          onPatch({ est_work_hours: next.trim() === "" ? null : Number(next) })
        }
      />
      <InlineTextField
        testId="item-actual-work-hours"
        label="实际工时（小时）"
        value={fields.actual_work_hours === null || fields.actual_work_hours === undefined
          ? ""
          : String(fields.actual_work_hours)}
        canEdit={canEdit}
        emptyText="—"
        inputType="number"
        editLabel="编辑实际工时"
        renderView={hoursText}
        onSave={(next) =>
          onPatch({ actual_work_hours: next.trim() === "" ? null : Number(next) })
        }
      />
      <InlineTextField
        testId="item-code-branch"
        label="代码分支"
        value={String(fields.code_branch ?? "")}
        canEdit={canEdit}
        emptyText="未填写"
        editLabel="编辑代码分支"
        onSave={(next) => onPatch({ code_branch: blankToNull(next) })}
      />
    </Stack>
  );
}
