import { useEffect, useState } from "react";

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
import { Stack } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import type { WorkItem } from "../types";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";

interface Props {
  open: boolean;
  item: WorkItem | null;
  onClose: () => void;
  onSaved: (item: WorkItem) => void;
}

const labelStyle = {
  display: "block",
  fontWeight: "var(--ds-font-weight-medium, 500)",
  marginBottom: 4,
} as const;

export default function EditWorkItemDialog({ open, item, onClose, onSaved }: Props) {
  const notify = useNotify();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(0);
  const [acceptance, setAcceptance] = useState("");
  const [issue, setIssue] = useState<IssueFields>({
    severity: "major",
    environment: "",
    repro: "",
  });
  const [task, setTask] = useState<TaskFields>({ task_type: "other", est_work_hours: 0 });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !item) return;
    setTitle(item.title);
    setDescription(item.description_md ?? "");
    setPriority(item.priority ?? 0);
    const f = (item.fields ?? {}) as Record<string, unknown>;
    setAcceptance((f.acceptance_criteria_md as string) || "");
    setIssue({
      severity: (f.severity as string) || "major",
      environment: (f.environment as string) || "",
      repro: (f.repro_steps_md as string) || "",
    });
    setTask({
      task_type: (f.task_type as string) || "other",
      est_work_hours: Number(f.est_work_hours ?? 0),
    });
  }, [open, item]);

  const save = async () => {
    if (!item || saving) return;
    setSaving(true);
    try {
      // Flat kind-specific fields per WorkItemUpdateIn; row_version required.
      const payload: Record<string, unknown> = {
        row_version: item.row_version,
        title,
        description_md: description,
        priority,
      };
      if (item.kind === "story") {
        payload.acceptance_criteria_md = acceptance;
      } else if (item.kind === "issue") {
        payload.severity = issue.severity;
        payload.environment = issue.environment;
        payload.repro_steps_md = issue.repro;
      } else if (item.kind === "task") {
        payload.task_type = task.task_type;
        payload.est_work_hours = task.est_work_hours;
      }
      const updated = (await api.patch<WorkItem>(`/work-items/${item.display_id}`, payload)).data;
      notify.success("已保存");
      onSaved(updated);
      onClose();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && item && (
        <ModalDialog onClose={onClose} width="560px">
          <ModalHeader>
            <ModalTitle>编辑工作项</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Stack space="space.050">
                <label htmlFor="wi-edit-title" style={labelStyle}>
                  标题
                </label>
                <Textfield
                  id="wi-edit-title"
                  value={title}
                  onChange={(e) => setTitle(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="wi-edit-desc" style={labelStyle}>
                  描述（Markdown）
                </label>
                <TextArea
                  id="wi-edit-desc"
                  value={description}
                  minimumRows={4}
                  onChange={(e) => setDescription(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="wi-edit-priority" style={labelStyle}>
                  优先级
                </label>
                <Textfield
                  id="wi-edit-priority"
                  type="number"
                  min={0}
                  max={99}
                  width={120}
                  value={priority}
                  onChange={(e) => setPriority(Number(e.currentTarget.value))}
                />
              </Stack>
              <KindSpecificFields
                kind={item.kind}
                acceptance={acceptance}
                onAcceptance={setAcceptance}
                issue={issue}
                onIssue={setIssue}
                task={task}
                onTask={setTask}
              />
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              取消
            </Button>
            <Button appearance="primary" isLoading={saving} onClick={save}>
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
