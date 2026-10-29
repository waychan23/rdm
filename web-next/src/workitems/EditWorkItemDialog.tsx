import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Stack } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import { portalMenuProps } from "../lib/portalMenu";
import type { WorkItem } from "../types";
import { allowedParentKinds } from "./parentRules";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";

interface Props {
  open: boolean;
  projectKey: string;
  item: WorkItem | null;
  parentOption?: WorkItemOption | null;
  onClose: () => void;
  onSaved: (item: WorkItem) => void;
}

export default function EditWorkItemDialog({
  open,
  projectKey,
  item,
  parentOption = null,
  onClose,
  onSaved,
}: Props) {
  const notify = useNotify();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(0);
  const [parent, setParent] = useState<WorkItemOption | null>(null);
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
    if (!open || !item) return;
    setTitle(item.title);
    setDescription(item.description_md ?? "");
    setPriority(item.priority ?? 0);
    setParent(parentOption);
    const f = (item.fields ?? {}) as Record<string, unknown>;
    setAcceptance((f.acceptance_criteria_md as string) || "");
    const sourceId = (f.source_story_id as string) || null;
    setIssue({
      severity: (f.severity as string) || "major",
      environment: (f.environment as string) || "",
      repro: (f.repro_steps_md as string) || "",
      expected: (f.expected_behavior_md as string) || "",
      actual: (f.actual_behavior_md as string) || "",
      sourceStory: sourceId
        ? {
            label: sourceId,
            value: sourceId,
            id: sourceId,
            display_id: sourceId,
            title: sourceId,
            kind: "story",
            status: "",
            row_version: 0,
          }
        : null,
    });
    setTask({
      task_type: (f.task_type as string) || "other",
      est_work_hours: Number(f.est_work_hours ?? 0),
    });
    // Re-seed only when the dialog opens or the underlying item changes; an
    // equal parent object is recreated on every ItemPanel render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, item, parentOption?.display_id]);

  const save = async () => {
    if (!item || saving) return;
    setSaving(true);
    try {
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
        payload.expected_behavior_md = issue.expected;
        payload.actual_behavior_md = issue.actual;
        payload.source_story = issue.sourceStory?.display_id ?? null;
      } else if (item.kind === "task") {
        payload.task_type = task.task_type;
        payload.est_work_hours = task.est_work_hours;
      }
      let updated = (
        await api.patch<WorkItem>(`/work-items/${item.display_id}`, payload)
      ).data;

      const wantedParent = parent?.display_id ?? null;
      const currentParent = parentOption?.display_id ?? null;
      if (wantedParent !== currentParent) {
        updated = (
          await api.post<WorkItem>(`/work-items/${item.display_id}/reparent`, {
            parent: wantedParent,
            row_version: updated.row_version,
          })
        ).data;
      }
      notify.success("已保存");
      onSaved(updated);
      onClose();
    } catch (e) {
      notify.error("保存失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  const parentKinds = item ? allowedParentKinds(item.kind) : [];

  return (
    <ModalTransition>
      {open && item && (
        <ModalDialog onClose={onClose} width="680px" testId="work-item-edit-dialog">
          <ModalHeader>
            <ModalTitle>编辑工作项</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label="标题" htmlFor="wi-edit-title">
                <Textfield
                  id="wi-edit-title"
                  value={title}
                  testId="work-item-edit-title"
                  onChange={(e) => setTitle(e.currentTarget.value)}
                />
              </FormField>
              <FormField label="描述（Markdown）">
                <MarkdownEditor
                  value={description}
                  onChange={setDescription}
                  projectKey={projectKey}
                  minimumRows={4}
                  testId="work-item-edit-description"
                />
              </FormField>
              <FormField label="优先级" htmlFor="wi-edit-priority">
                <Textfield
                  id="wi-edit-priority"
                  type="number"
                  min={0}
                  max={999}
                  width={120}
                  value={priority}
                  testId="work-item-edit-priority"
                  onChange={(e) => setPriority(Number(e.currentTarget.value))}
                />
              </FormField>
              {parentKinds.length > 0 && (
                <FormField label="父项">
                  <WorkItemPicker
                    projectKey={projectKey}
                    allowedKinds={parentKinds}
                    excludeIds={[item.id]}
                    value={parent}
                    onChange={setParent}
                    placeholder="选择父项（可清除）"
                    testId="work-item-edit-parent"
                  />
                </FormField>
              )}
              <KindSpecificFields
                kind={item.kind}
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
            <Button appearance="subtle" onClick={onClose} testId="work-item-edit-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              testId="work-item-edit-submit"
              onClick={() => void save()}
            >
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
