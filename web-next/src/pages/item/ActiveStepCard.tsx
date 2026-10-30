import Button from "@atlaskit/button/default/button";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import SectionMessage from "@atlaskit/section-message";

import MarkdownText from "../../components/MarkdownText";
import PersonCell from "../../components/PersonCell";
import TextButton from "../../components/TextButton";
import { statusLabel } from "../../lib/labels";
import StatusLozenge from "../../workitems/status";
import type { ActiveStep } from "../../types";

interface Props {
  step: ActiveStep;
  onExecute: () => void;
  onReject: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onReassign: () => void;
  onOpenItem: (id: string) => void;
}

export default function ActiveStepCard({
  step,
  onExecute,
  onReject,
  onCancel,
  onRetry,
  onReassign,
  onOpenItem,
}: Props) {
  const done = step.executors.filter((executor) => executor.status === "DONE").length;
  const missing =
    (step.gate_details?.missing_fields as { key: string; label: string }[] | undefined) ?? [];

  return (
    <Stack space="space.100" testId="active-step-card">
      <Inline space="space.100" alignBlock="center" shouldWrap>
        <Text weight="medium">{step.name}</Text>
        <StatusLozenge status={step.status} />
        <Text size="small" color="color.text.subtlest">
          → {statusLabel(step.to)}
        </Text>
      </Inline>
      <Text size="small" color="color.text.subtle">
        执行进度 {done}/{step.required_count}
        {step.mode === "task" ? "（任务式步骤）" : ""}
      </Text>
      {step.executors.map((executor) => (
        <div key={executor.id} className="rdm-step-executor">
          <Inline space="space.100" alignBlock="center" shouldWrap>
            <PersonCell name={executor.user.name ?? executor.user.id} />
            <StatusLozenge status={executor.status} />
            {executor.task && executor.task_id && (
              <TextButton onClick={() => onOpenItem(executor.task_id as string)}>
                子任务：{executor.task.title}（{statusLabel(executor.task.status)}）
              </TextButton>
            )}
          </Inline>
          {executor.note_md && (
            <div className="rdm-step-note">
              <MarkdownText source={executor.note_md} />
            </div>
          )}
        </div>
      ))}
      {missing.length > 0 && (
        <SectionMessage appearance="warning">
          缺少必填字段：{missing.map((field) => field.label).join("、")}
        </SectionMessage>
      )}
      <Inline space="space.100" shouldWrap>
        {step.can_execute && (
          <Button appearance="primary" spacing="compact" onClick={onExecute} testId="step-active-execute">
            执行步骤
          </Button>
        )}
        {step.can_reject && (
          <Button appearance="danger" spacing="compact" onClick={onReject} testId="step-active-reject">
            拒绝
          </Button>
        )}
        {step.can_retry && (
          <Button appearance="primary" spacing="compact" onClick={onRetry} testId="step-active-retry">
            重试
          </Button>
        )}
        {step.can_reassign && (
          <Button spacing="compact" onClick={onReassign} testId="step-active-reassign">
            改派执行人
          </Button>
        )}
        {step.can_cancel && (
          <Button appearance="subtle" spacing="compact" onClick={onCancel} testId="step-active-cancel">
            取消步骤
          </Button>
        )}
      </Inline>
    </Stack>
  );
}
