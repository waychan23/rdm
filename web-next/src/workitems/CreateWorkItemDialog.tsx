import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Stack, Text } from "@atlaskit/primitives/compiled";
import { RadioGroup } from "@atlaskit/radio";
import Textfield from "@atlaskit/textfield";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import type { WorkItem } from "../types";
import { KIND_OPTIONS } from "./constants";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";
import { allowedParentKinds } from "./parentRules";

interface Props {
  open: boolean;
  projectKey: string;
  initialParent?: WorkItemOption | null;
  allowedKinds?: string[];
  onClose: () => void;
  onCreated: (item: WorkItem) => void;
}

export default function CreateWorkItemDialog({
  open,
  projectKey,
  initialParent = null,
  allowedKinds,
  onClose,
  onCreated,
}: Props) {
  const notify = useNotify();
  const kinds = allowedKinds ?? KIND_OPTIONS.map((k) => k.value);
  const allowedKey = allowedKinds?.join(",") ?? "";
  const [kind, setKind] = useState(allowedKinds?.[0] ?? "task");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(0);
  const [parent, setParent] = useState<WorkItemOption | null>(initialParent);
  const [acceptance, setAcceptance] = useState("");
  const [issue, setIssue] = useState<IssueFields>({
    severity: "major",
    environment: "",
    repro: "",
    expected: "",
    actual: "",
    sourceStory: null,
  });
  const [task, setTask] = useState<TaskFields>({ task_type: "other", est_work_hours: 0 });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setKind(allowedKinds?.[0] ?? "task");
    setTitle("");
    setDescription("");
    setPriority(0);
    setParent(initialParent);
    setAcceptance("");
    setIssue({
      severity: "major",
      environment: "",
      repro: "",
      expected: "",
      actual: "",
      sourceStory: null,
    });
    setTask({ task_type: "other", est_work_hours: 0 });
    // Callers may pass inline arrays; only re-seed on open / kind-set change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, allowedKey, initialParent?.display_id]);

  // Switching kind can invalidate the currently selected parent.
  useEffect(() => {
    if (parent && !allowedParentKinds(kind).includes(parent.kind)) {
      setParent(null);
    }
  }, [kind, parent]);

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
      if (parent) payload.parent = parent.display_id;
      if (kind === "story") payload.acceptance_criteria_md = acceptance;
      if (kind === "issue") {
        payload.severity = issue.severity;
        payload.environment = issue.environment;
        payload.repro_steps_md = issue.repro;
        payload.expected_behavior_md = issue.expected;
        payload.actual_behavior_md = issue.actual;
        if (issue.sourceStory) payload.source_story = issue.sourceStory.display_id;
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

  const parentKinds = allowedParentKinds(kind);
  const kindOptions = KIND_OPTIONS.filter((option) => kinds.includes(option.value));

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="680px" testId="work-item-create-dialog">
          <ModalHeader>
            <ModalTitle>新建工作项</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Stack space="space.050">
                <Text size="small" weight="medium" color="color.text.subtle">
                  类型
                </Text>
                <RadioGroup
                  options={kindOptions.map((k) => ({
                    name: "kind",
                    value: k.value,
                    label: k.label,
                  }))}
                  value={kind}
                  onChange={(e) => setKind(e.currentTarget.value)}
                />
              </Stack>
              <FormField label="标题" htmlFor="wi-title">
                <Textfield
                  id="wi-title"
                  value={title}
                  placeholder="工作项标题"
                  testId="work-item-create-title"
                  onChange={(e) => setTitle(e.currentTarget.value)}
                  onKeyDown={(e) => e.key === "Enter" && void submit()}
                />
              </FormField>
              <FormField label="描述（Markdown）">
                <MarkdownEditor
                  value={description}
                  onChange={setDescription}
                  projectKey={projectKey}
                  minimumRows={4}
                  testId="work-item-create-description"
                />
              </FormField>
              <FormField label="优先级" htmlFor="wi-priority">
                <Textfield
                  id="wi-priority"
                  type="number"
                  min={0}
                  max={999}
                  width={120}
                  value={priority}
                  testId="work-item-create-priority"
                  onChange={(e) => setPriority(Number(e.currentTarget.value))}
                />
              </FormField>
              {parentKinds.length > 0 && (
                <FormField label="父项（可空）">
                  <WorkItemPicker
                    projectKey={projectKey}
                    allowedKinds={parentKinds}
                    value={parent}
                    onChange={setParent}
                    placeholder="选择父项"
                    testId="work-item-create-parent"
                  />
                </FormField>
              )}
              <KindSpecificFields
                kind={kind}
                projectKey={projectKey}
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
            <Button appearance="subtle" onClick={onClose} testId="work-item-create-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              testId="work-item-create-submit"
              onClick={() => void submit()}
            >
              创建
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
