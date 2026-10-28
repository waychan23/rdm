import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { RadioGroup } from "@atlaskit/radio";
import Textfield from "@atlaskit/textfield";
import TextArea from "@atlaskit/textarea";
import { Stack } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import type { WorkItem } from "../types";
import { KIND_OPTIONS } from "./constants";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";

interface Props {
  open: boolean;
  projectKey: string;
  onClose: () => void;
  onCreated: (item: WorkItem) => void;
}

const labelStyle = {
  display: "block",
  fontWeight: "var(--ds-font-weight-medium, 500)",
  marginBottom: 4,
} as const;

export default function CreateWorkItemDialog({ open, projectKey, onClose, onCreated }: Props) {
  const notify = useNotify();
  const [kind, setKind] = useState("task");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(0);
  const [parentRef, setParentRef] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [issue, setIssue] = useState<IssueFields>({
    severity: "major",
    environment: "",
    repro: "",
  });
  const [task, setTask] = useState<TaskFields>({ task_type: "other", est_work_hours: 0 });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setTitle("");
      setDescription("");
      setPriority(0);
      setParentRef("");
      setAcceptance("");
    }
  }, [open]);

  const submit = async () => {
    if (!title.trim()) {
      notify.error("请填写标题");
      return;
    }
    if (saving) return;
    setSaving(true);
    try {
      // Flat kind-specific fields per WorkItemCreateIn (schemas.py).
      const payload: Record<string, unknown> = {
        kind,
        title,
        description_md: description,
        priority,
      };
      if (parentRef.trim()) payload.parent = parentRef.trim();
      if (kind === "story") payload.acceptance_criteria_md = acceptance;
      if (kind === "issue") {
        payload.severity = issue.severity;
        payload.environment = issue.environment;
        payload.repro_steps_md = issue.repro;
      }
      if (kind === "task") {
        payload.task_type = task.task_type;
        payload.est_work_hours = task.est_work_hours;
      }
      const item = (
        await api.post<WorkItem>(`/projects/${projectKey}/work-items`, payload)
      ).data;
      notify.success(`已创建 ${item.display_id}`);
      onCreated(item);
      onClose();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="520px">
          <ModalHeader>
            <ModalTitle>新建工作项</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <div>
                <span style={labelStyle}>类型</span>
                <RadioGroup
                  options={KIND_OPTIONS.map((k) => ({ name: "kind", value: k.value, label: k.label }))}
                  value={kind}
                  onChange={(e) => setKind(e.currentTarget.value)}
                />
              </div>
              <Stack space="space.050">
                <label htmlFor="wi-title" style={labelStyle}>
                  标题
                </label>
                <Textfield
                  id="wi-title"
                  value={title}
                  placeholder="工作项标题"
                  onChange={(e) => setTitle(e.currentTarget.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="wi-desc" style={labelStyle}>
                  描述（Markdown）
                </label>
                <TextArea
                  id="wi-desc"
                  value={description}
                  minimumRows={4}
                  onChange={(e) => setDescription(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="wi-priority" style={labelStyle}>
                  优先级
                </label>
                <Textfield
                  id="wi-priority"
                  type="number"
                  min={0}
                  max={99}
                  width={120}
                  value={priority}
                  onChange={(e) => setPriority(Number(e.currentTarget.value))}
                />
              </Stack>
              {kind !== "epic" && (
                <Stack space="space.050">
                  <label htmlFor="wi-parent" style={labelStyle}>
                    父项（display id，可空）
                  </label>
                  <Textfield
                    id="wi-parent"
                    value={parentRef}
                    placeholder="如 RDM-12"
                    onChange={(e) => setParentRef(e.currentTarget.value)}
                  />
                </Stack>
              )}
              <KindSpecificFields
                kind={kind}
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
            <Button appearance="primary" isLoading={saving} onClick={submit}>
              创建
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
