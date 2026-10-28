import { useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Textfield from "@atlaskit/textfield";
import TextArea from "@atlaskit/textarea";
import { DatePicker } from "@atlaskit/datetime-picker";
import { Stack } from "@atlaskit/primitives";

export interface SprintFormValues {
  name: string;
  goal_md: string;
  start_date: string | null;
  end_date: string | null;
}

interface Props {
  open: boolean;
  title: string;
  initial?: Partial<SprintFormValues>;
  onClose: () => void;
  onSave: (values: SprintFormValues) => Promise<void> | void;
}

const labelStyle = {
  display: "block",
  fontWeight: "var(--ds-font-weight-medium, 500)",
  marginBottom: 4,
} as const;

export default function SprintFormDialog({ open, title, initial, onClose, onSave }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [goal, setGoal] = useState(initial?.goal_md ?? "");
  const [start, setStart] = useState(initial?.start_date ?? "");
  const [end, setEnd] = useState(initial?.end_date ?? "");
  const [saving, setSaving] = useState(false);

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="440px">
          <ModalHeader>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Stack space="space.050">
                <label htmlFor="sprint-name" style={labelStyle}>
                  名称
                </label>
                <Textfield
                  id="sprint-name"
                  value={name}
                  autoFocus
                  onChange={(e) => setName(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="sprint-goal" style={labelStyle}>
                  目标（Markdown）
                </label>
                <TextArea
                  id="sprint-goal"
                  value={goal}
                  minimumRows={3}
                  onChange={(e) => setGoal(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <span style={labelStyle}>起止日期</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <DatePicker
                    placeholder="开始"
                    value={start || ""}
                    onChange={(v) => setStart(v)}
                  />
                  <DatePicker
                    placeholder="结束"
                    value={end || ""}
                    onChange={(v) => setEnd(v)}
                  />
                </div>
              </Stack>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={async () => {
                if (!name.trim()) return;
                setSaving(true);
                await onSave({
                  name: name.trim(),
                  goal_md: goal,
                  start_date: start || null,
                  end_date: end || null,
                });
              }}
            >
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
