import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import { useTranslation } from "react-i18next";

import { statusLabel } from "../../lib/labels";
import { portalMenuProps } from "../../lib/portalMenu";
import { userLabel } from "../../lib/users";
import type { WorkflowStepDef } from "../../types";

interface Props {
  open: boolean;
  step: WorkflowStepDef | null;
  mode?: "start" | "reassign";
  onClose: () => void;
  onConfirm: (executors: string[]) => Promise<void>;
}

interface Option {
  label: string;
  value: string;
}

export default function StepStartDialog({
  open,
  step,
  mode = "start",
  onClose,
  onConfirm,
}: Props) {
  const { t } = useTranslation("item");
  const [selected, setSelected] = useState<Option[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !step) return;
    setSelected(
      step.auto_executors.map((user) => ({
        label: userLabel(user) || user.id,
        value: user.id,
      })),
    );
    setSaving(false);
  }, [open, step]);

  if (!step) return null;
  const options: Option[] = step.candidates.map((user) => ({
    label: `${userLabel(user) || user.id}${user.type === "agent" ? t("panel.agentSuffix") : ""}`,
    value: user.id,
  }));
  const max = step.executors.max ?? step.candidates.length;
  const count = selected.length;
  const invalid = count < step.executors.min || count > max;

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="560px" testId="step-start-dialog">
          <ModalHeader>
            <ModalTitle>
              {mode === "reassign"
                ? t("stepStart.reassignTitle", { name: step.name })
                : t("stepStart.startTitle", { name: step.name })}
            </ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Text size="small" color="color.text.subtlest">
                {t("stepStart.targetStatus", { status: statusLabel(step.to) })} ·{" "}
                {step.mode === "task"
                  ? t("stepStart.taskMode")
                  : t("stepStart.approvalMode")}
              </Text>
              <Text size="small" color="color.text.subtlest">
                {t("stepStart.executorsHint", {
                  min: step.executors.min,
                  max,
                  sources:
                    (step.actor_sources ?? []).join(" / ") || t("stepStart.notConfigured"),
                })}
                {step.mode === "task" && step.tasks
                  ? t("stepStart.taskLine", {
                      type: step.tasks.type,
                      condition: step.tasks.complete_on,
                    })
                  : ""}
              </Text>
              <div>
                <Text size="small" weight="medium" color="color.text.subtle">
                  {t("stepStart.executorsLabel")}
                </Text>
                <Select
                  {...portalMenuProps}
                  isMulti
                  options={options}
                  value={selected}
                  placeholder={t("stepStart.executorsPlaceholder")}
                  testId="step-start-executors"
                  onChange={(value) => setSelected([...(value ?? [])] as Option[])}
                />
              </div>
              {options.length === 0 && (
                <Text size="small" color="color.text.danger">
                  {t("stepStart.noCandidates")}
                </Text>
              )}
              {count > max && (
                <Text size="small" color="color.text.danger">
                  {t("stepStart.maxSelect", { max })}
                </Text>
              )}
              {count < step.executors.min && (
                <Text size="small" color="color.text.danger">
                  {t("stepStart.minSelect", { min: step.executors.min })}
                </Text>
              )}
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Inline space="space.100">
              <Button appearance="subtle" onClick={onClose} testId="step-start-cancel">
                {t("stepStart.cancel")}
              </Button>
              <Button
                appearance="primary"
                isLoading={saving}
                isDisabled={invalid || options.length === 0}
                testId="step-start-confirm"
                onClick={async () => {
                  setSaving(true);
                  try {
                    await onConfirm(selected.map((option) => option.value));
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                {mode === "reassign" ? t("stepStart.save") : t("stepStart.start")}
              </Button>
            </Inline>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
