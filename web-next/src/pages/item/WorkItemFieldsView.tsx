import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import type { ReactNode } from "react";

import MarkdownText from "../../components/MarkdownText";
import TextButton from "../../components/TextButton";
import type { WorkItem } from "../../types";
import type { MarkdownImageClick } from "../../components/MarkdownText";

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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rdm-item-kind-field">
      <div className="rdm-item-section-label">{label}</div>
      {children}
    </div>
  );
}

function Empty() {
  return (
    <Text size="small" color="color.text.subtlest">
      未填写
    </Text>
  );
}

interface Props {
  item: WorkItem;
  onOpenItem: (id: string) => void;
  onImageClick: (image: MarkdownImageClick) => void;
}

export default function WorkItemFieldsView({ item, onOpenItem, onImageClick }: Props) {
  const fields = (item.fields ?? {}) as Record<string, unknown>;
  if (item.kind === "epic" || Object.keys(fields).length === 0) {
    return (
      <Text size="small" color="color.text.subtlest">
        该类型没有额外字段
      </Text>
    );
  }

  if (item.kind === "story") {
    const acceptance = fields.acceptance_criteria_md as string | undefined;
    return (
      <Field label="验收标准">
        {acceptance ? (
          <MarkdownText source={acceptance} onImageClick={onImageClick} />
        ) : (
          <Empty />
        )}
      </Field>
    );
  }

  if (item.kind === "issue") {
    const sourceStoryId = fields.source_story_id as string | undefined;
    return (
      <Stack space="space.150">
        <Field label="严重度">
          <Text size="small">{String(fields.severity ?? "major")}</Text>
        </Field>
        <Field label="环境">
          {fields.environment ? (
            <Text size="small">{String(fields.environment)}</Text>
          ) : (
            <Empty />
          )}
        </Field>
        <Field label="来源 story">
          {sourceStoryId ? (
            <TextButton onClick={() => onOpenItem(sourceStoryId)}>
              {sourceStoryId}
            </TextButton>
          ) : (
            <Empty />
          )}
        </Field>
        {(
          [
            ["repro_steps_md", "复现步骤"],
            ["expected_behavior_md", "期望行为"],
            ["actual_behavior_md", "实际行为"],
          ] as const
        ).map(([key, label]) => {
          const value = fields[key] as string | undefined;
          return (
            <Field key={key} label={label}>
              {value ? (
                <MarkdownText source={value} onImageClick={onImageClick} />
              ) : (
                <Empty />
              )}
            </Field>
          );
        })}
      </Stack>
    );
  }

  const hours = (value: unknown) => (value === null || value === undefined ? "—" : `${value}h`);
  return (
    <Stack space="space.150">
      <Field label="任务类型">
        <Text size="small">
          {TASK_TYPES[String(fields.task_type ?? "other")] ?? String(fields.task_type ?? "—")}
        </Text>
      </Field>
      <Field label="预估 / 实际工时">
        <Inline space="space.100">
          <Text size="small">{hours(fields.est_work_hours)}</Text>
          <Text size="small" color="color.text.subtlest">
            /
          </Text>
          <Text size="small">{hours(fields.actual_work_hours)}</Text>
        </Inline>
      </Field>
      <Field label="代码分支">
        {fields.code_branch ? (
          <Text size="small">{String(fields.code_branch)}</Text>
        ) : (
          <Empty />
        )}
      </Field>
    </Stack>
  );
}
