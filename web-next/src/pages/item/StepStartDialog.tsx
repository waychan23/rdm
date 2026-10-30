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

import { portalMenuProps } from "../../lib/portalMenu";
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
  const [selected, setSelected] = useState<Option[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !step) return;
    setSelected(
      step.auto_executors.map((user) => ({
        label: user.name ?? user.id,
        value: user.id,
      })),
    );
    setSaving(false);
  }, [open, step]);

  if (!step) return null;
  const options: Option[] = step.candidates.map((user) => ({
    label: `${user.name ?? user.id}${user.type === "agent" ? "（agent）" : ""}`,
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
              {mode === "reassign" ? "改派执行人" : "发起步骤"} · {step.name}
            </ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Text size="small" color="color.text.subtlest">
                目标状态：{step.to} ·{" "}
                {step.mode === "task"
                  ? "任务式步骤：将为每名执行人创建一个子任务"
                  : "多人步骤：所有执行人都提交后才自动流转"}
              </Text>
              <Text size="small" color="color.text.subtlest">
                需要 {step.executors.min}–{max} 名执行人；候选人来自{" "}
                {(step.actor_sources ?? []).join(" / ") || "（未配置）"}。
                {step.mode === "task" && step.tasks
                  ? ` 子任务类型：${step.tasks.type}，完成条件：${step.tasks.complete_on}。`
                  : ""}
              </Text>
              <div>
                <Text size="small" weight="medium" color="color.text.subtle">
                  执行人
                </Text>
                <Select
                  {...portalMenuProps}
                  isMulti
                  options={options}
                  value={selected}
                  placeholder="选择执行人"
                  testId="step-start-executors"
                  onChange={(value) => setSelected([...(value ?? [])] as Option[])}
                />
              </div>
              {options.length === 0 && (
                <Text size="small" color="color.text.danger">
                  没有候选执行人：请先维护 reviewer / 参与人，或指派负责人。
                </Text>
              )}
              {count > max && (
                <Text size="small" color="color.text.danger">
                  最多选择 {max} 人。
                </Text>
              )}
              {count < step.executors.min && (
                <Text size="small" color="color.text.danger">
                  至少选择 {step.executors.min} 人。
                </Text>
              )}
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Inline space="space.100">
              <Button appearance="subtle" onClick={onClose} testId="step-start-cancel">
                取消
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
                {mode === "reassign" ? "保存" : "发起"}
              </Button>
            </Inline>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
