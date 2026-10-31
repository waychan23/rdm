import Button from "@atlaskit/button/default/button";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import SectionMessage from "@atlaskit/section-message";
import { useTranslation } from "react-i18next";

import MarkdownText from "../../components/MarkdownText";
import PersonCell from "../../components/PersonCell";
import TextButton from "../../components/TextButton";
import { statusLabel } from "../../lib/labels";
import { userLabel } from "../../lib/users";
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
  const { t } = useTranslation("item");
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
        {t("activeStep.progress", { done, required: step.required_count })}
        {step.mode === "task" ? t("activeStep.taskModeSuffix") : ""}
      </Text>
      {step.executors.map((executor) => (
        <div key={executor.id} className="rdm-step-executor">
          <Inline space="space.100" alignBlock="center" shouldWrap>
            <PersonCell name={userLabel(executor.user) || executor.user.id} />
            <StatusLozenge status={executor.status} />
            {executor.task && executor.task_id && (
              <TextButton onClick={() => onOpenItem(executor.task_id as string)}>
                {t("activeStep.subtask", {
                  title: executor.task.title,
                  status: statusLabel(executor.task.status),
                })}
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
          {t("activeStep.missing", {
            fields: missing.map((field) => field.label).join(t("listSeparator")),
          })}
        </SectionMessage>
      )}
      <Inline space="space.100" shouldWrap>
        {step.can_execute && (
          <Button appearance="primary" spacing="compact" onClick={onExecute} testId="step-active-execute">
            {t("activeStep.execute")}
          </Button>
        )}
        {step.can_reject && (
          <Button appearance="danger" spacing="compact" onClick={onReject} testId="step-active-reject">
            {t("activeStep.reject")}
          </Button>
        )}
        {step.can_retry && (
          <Button appearance="primary" spacing="compact" onClick={onRetry} testId="step-active-retry">
            {t("activeStep.retry")}
          </Button>
        )}
        {step.can_reassign && (
          <Button spacing="compact" onClick={onReassign} testId="step-active-reassign">
            {t("activeStep.reassign")}
          </Button>
        )}
        {step.can_cancel && (
          <Button appearance="subtle" spacing="compact" onClick={onCancel} testId="step-active-cancel">
            {t("activeStep.cancel")}
          </Button>
        )}
      </Inline>
    </Stack>
  );
}
