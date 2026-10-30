import { useEffect, useMemo, useState } from "react";

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
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { api, errorCause } from "../lib/api";
import { useCurrentUser } from "../lib/auth";
import { useNotify } from "../lib/flags";
import { portalMenuProps } from "../lib/portalMenu";
import type { WorkflowDto, WorkflowFields, WorkItem } from "../types";
import { KIND_OPTIONS, TASK_TYPE_OPTIONS } from "./constants";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";
import { allowedParentKinds } from "./parentRules";
import WorkItemPeopleFields, {
  emptyOptionalValues,
  type OptionalFieldValues,
} from "./WorkItemPeopleFields";

interface Props {
  open: boolean;
  projectKey: string;
  initialParent?: WorkItemOption | null;
  allowedKinds?: string[];
  parentLocked?: boolean;
  dialogTitle?: string;
  onClose: () => void;
  onCreated: (item: WorkItem) => void;
}

const EMPTY_FIELDS: WorkflowFields = {
  reviewer: false,
  review_content: false,
  custom: [],
};

function resolveFields(
  workflow: WorkflowDto | null,
  kind: string,
  taskType: string,
): WorkflowFields {
  const kindSpec = workflow?.kinds[kind];
  if (!kindSpec) return EMPTY_FIELDS;
  const effective =
    kind === "task" && kindSpec.subtypes?.[taskType]
      ? kindSpec.subtypes[taskType]
      : kindSpec;
  return effective.fields ?? EMPTY_FIELDS;
}

export default function CreateWorkItemDialog({
  open,
  projectKey,
  initialParent = null,
  allowedKinds,
  parentLocked = false,
  dialogTitle = "新建工作项",
  onClose,
  onCreated,
}: Props) {
  const notify = useNotify();
  const me = useCurrentUser();
  const identityId = me?.identity.id ?? null;
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
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(null);
  const [people, setPeople] = useState<OptionalFieldValues>(emptyOptionalValues(null));
  const [saving, setSaving] = useState(false);
  const fields = useMemo(
    () => resolveFields(workflow, kind, task.task_type),
    [workflow, kind, task.task_type],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api
      .get<WorkflowDto>("/workflow")
      .then((res) => {
        if (!cancelled) setWorkflow(res.data);
      })
      .catch(() => {
        if (!cancelled) setWorkflow(null);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

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
    setPeople(emptyOptionalValues(identityId));
    // Callers may pass inline arrays; only re-seed on open / kind-set change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, allowedKey, initialParent?.display_id, identityId]);

  // Subtype changes can invalidate optional/custom field values.
  useEffect(() => {
    setPeople((current) => ({
      ...current,
      reviewer: [],
      reviewContent: "",
      custom: {},
    }));
  }, [kind, task.task_type]);

  // Switching kind can invalidate the currently selected parent. A child-add
  // dialog locks the parent, so never clear it there.
  useEffect(() => {
    if (parentLocked) return;
    if (parent && !allowedParentKinds(kind).includes(parent.kind)) {
      setParent(null);
    }
  }, [kind, parent, parentLocked]);

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
      const parentRef = parentLocked ? initialParent : parent;
      if (parentRef) payload.parent = parentRef.display_id;
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
      payload.participants = people.participants;
      if (people.assignee) payload.assignee = people.assignee;
      if (fields.reviewer) payload.reviewer = people.reviewer;
      if (fields.review_content) payload.review_content_md = people.reviewContent;
      if (fields.custom.length > 0) {
        payload.custom_fields = Object.fromEntries(
          fields.custom.map((field) => [field.key, people.custom[field.key] ?? null]),
        );
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

  const parentKinds = parentLocked ? [] : allowedParentKinds(kind);
  const kindOptions = KIND_OPTIONS.filter((option) => kinds.includes(option.value));

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="680px" testId="work-item-create-dialog">
          <ModalHeader>
            <ModalTitle>{dialogTitle}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              {parentLocked && initialParent && (
                <Text size="small" color="color.text.subtlest">
                  父项：{initialParent.display_id} · {initialParent.title}
                </Text>
              )}
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
              {kind === "task" && (
                <FormField label="任务类型" htmlFor="wi-create-task-type">
                  <Select
                    {...portalMenuProps}
                    inputId="wi-create-task-type"
                    options={TASK_TYPE_OPTIONS}
                    value={TASK_TYPE_OPTIONS.find((option) => option.value === task.task_type)}
                    testId="work-item-create-task-type"
                    onChange={(option) =>
                      option &&
                      setTask({
                        ...task,
                        task_type: (option as { value: string }).value,
                      })
                    }
                  />
                </FormField>
              )}
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
                hideTaskType
              />
              <WorkItemPeopleFields
                projectKey={projectKey}
                fields={fields}
                value={people}
                onChange={setPeople}
                showAssignee
                assigneeLabel="负责人（默认当前创建人，可修改）"
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
