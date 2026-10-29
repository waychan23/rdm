import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { DatePicker } from "@atlaskit/datetime-picker";
import { Inline, Stack } from "@atlaskit/primitives/compiled";
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";

import FormField from "../../components/FormField";

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

export default function SprintFormDialog({ open, title, initial, onClose, onSave }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [goal, setGoal] = useState(initial?.goal_md ?? "");
  const [start, setStart] = useState(initial?.start_date ?? "");
  const [end, setEnd] = useState(initial?.end_date ?? "");
  const [saving, setSaving] = useState(false);

  // The dialog component stays mounted while closed; reload the form from
  // `initial` every time it opens so edit reflects the selected sprint.
  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setGoal(initial?.goal_md ?? "");
    setStart(initial?.start_date ?? "");
    setEnd(initial?.end_date ?? "");
    setSaving(false);
    // `initial` is a fresh object each render; only re-seed on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        goal_md: goal,
        start_date: start || null,
        end_date: end || null,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="440px" testId="sprint-form-dialog">
          <ModalHeader>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label="名称" htmlFor="sprint-name">
                <Textfield
                  id="sprint-name"
                  value={name}
                  autoFocus
                  testId="sprint-form-name"
                  onChange={(e) => setName(e.currentTarget.value)}
                />
              </FormField>
              <FormField label="目标（Markdown）" htmlFor="sprint-goal">
                <TextArea
                  id="sprint-goal"
                  value={goal}
                  minimumRows={3}
                  testId="sprint-form-goal"
                  onChange={(e) => setGoal(e.currentTarget.value)}
                />
              </FormField>
              <FormField label="起止日期">
                <Inline space="space.100">
                  <DatePicker
                    placeholder="开始"
                    value={start || ""}
                    testId="sprint-form-start"
                    onChange={(v) => setStart(v)}
                  />
                  <DatePicker
                    placeholder="结束"
                    value={end || ""}
                    testId="sprint-form-end"
                    onChange={(v) => setEnd(v)}
                  />
                </Inline>
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="sprint-form-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={() => void submit()}
              testId="sprint-form-submit"
            >
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
