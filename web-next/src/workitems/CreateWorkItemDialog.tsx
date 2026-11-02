import { useEffect, useMemo, useState } from "react";

import Button from "@atlaskit/button/default/button";
import { DatePicker } from "@atlaskit/datetime-picker";
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
import { useTranslation } from "react-i18next";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { api, errorCause } from "../lib/api";
import { useCurrentUser } from "../lib/auth";
import { useNotify } from "../lib/flags";
import { parseHoursInput } from "../lib/format";
import { portalMenuProps } from "../lib/portalMenu";
import type { WorkflowDto, WorkflowFields, WorkItem } from "../types";
import { kindOptions, taskTypeOptions } from "./constants";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";
import { allowedParentKinds } from "./parentRules";
import { DEFAULT_PRIORITY, priorityOptions } from "./priority";
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
  dialogTitle,
  onClose,
  onCreated,
}: Props) {
  const { t } = useTranslation("workitems");
  const notify = useNotify();
  const me = useCurrentUser();
  const identityId = me?.identity.id ?? null;
  const kinds = allowedKinds ?? kindOptions().map((k) => k.value);
  const allowedKey = allowedKinds?.join(",") ?? "";
  const [kind, setKind] = useState(allowedKinds?.[0] ?? "task");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(DEFAULT_PRIORITY);
  const [plannedStart, setPlannedStart] = useState("");
  const [plannedEnd, setPlannedEnd] = useState("");
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
  const [task, setTask] = useState<TaskFields>({ task_type: "other", est_work_hours: "0" });
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(null);
  const [people, setPeople] = useState<OptionalFieldValues>(emptyOptionalValues(null));
  const [saving, setSaving] = useState(false);
  const fields = useMemo(
    () => resolveFields(workflow, kind, task.task_type),
    [workflow, kind, task.task_type],
  );
  // The config's task_types are authoritative: the web UI must not offer a
  // type the selected workflow does not define (RDM-85).
  const taskTypeChoices = useMemo(
    () => (workflow?.task_types?.length ? workflow.task_types : taskTypeOptions()),
    [workflow],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api
      .get<WorkflowDto>(`/workflow?project=${encodeURIComponent(projectKey)}`)
      .then((res) => {
        if (!cancelled) setWorkflow(res.data);
      })
      .catch(() => {
        if (!cancelled) setWorkflow(null);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectKey]);

  useEffect(() => {
    if (!open) return;
    // Story/task may now also hold defects; keep subtasks as the default child.
    const prefersTask =
      parentLocked &&
      (initialParent?.kind === "story" || initialParent?.kind === "task") &&
      allowedKinds?.includes("task");
    const defaultKind = prefersTask ? "task" : (allowedKinds?.[0] ?? "task");
    setKind(defaultKind);
    setTitle("");
    setDescription("");
    setPriority(DEFAULT_PRIORITY);
    setPlannedStart("");
    setPlannedEnd("");
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
    setTask({ task_type: "other", est_work_hours: "0" });
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
      notify.error(t("create.requiredTitle"));
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
        planned_start_date: plannedStart || null,
        planned_end_date: plannedEnd || null,
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
        payload.est_work_hours = parseHoursInput(task.est_work_hours);
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
      notify.success(t("create.created", { id: item.display_id }));
      onCreated(item);
      onClose();
    } catch (e) {
      notify.error(t("create.createFailed"), errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  const parentKinds = parentLocked ? [] : allowedParentKinds(kind);
  const kindChoices = kindOptions().filter((option) => kinds.includes(option.value));

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="680px" testId="work-item-create-dialog">
          <ModalHeader>
            <ModalTitle>{dialogTitle ?? t("create.title")}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              {parentLocked && initialParent && (
                <Text size="small" color="color.text.subtlest">
                  {t("create.parentLine", {
                    id: initialParent.display_id,
                    title: initialParent.title,
                  })}
                </Text>
              )}
              <Stack space="space.050">
                <Text size="small" weight="medium" color="color.text.subtle">
                  {t("create.kind")}
                </Text>
                <RadioGroup
                  options={kindChoices.map((k) => ({
                    name: "kind",
                    value: k.value,
                    label: k.label,
                  }))}
                  value={kind}
                  onChange={(e) => setKind(e.currentTarget.value)}
                />
              </Stack>
              {kind === "task" && (
                <FormField label={t("create.taskType")} htmlFor="wi-create-task-type">
                  <Select
                    {...portalMenuProps}
                    inputId="wi-create-task-type"
                    options={taskTypeChoices}
                    value={taskTypeChoices.find((option) => option.value === task.task_type)}
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
              <FormField label={t("create.titleLabel")} htmlFor="wi-title">
                <Textfield
                  id="wi-title"
                  value={title}
                  placeholder={t("create.titlePlaceholder")}
                  testId="work-item-create-title"
                  onChange={(e) => setTitle(e.currentTarget.value)}
                  onKeyDown={(e) => e.key === "Enter" && void submit()}
                />
              </FormField>
              <FormField label={t("create.description")}>
                <MarkdownEditor
                  value={description}
                  onChange={setDescription}
                  projectKey={projectKey}
                  minimumRows={4}
                  testId="work-item-create-description"
                />
              </FormField>
              <FormField label={t("create.priority")} htmlFor="wi-priority">
                <Select
                  {...portalMenuProps}
                  inputId="wi-priority"
                  options={priorityOptions()}
                  value={priorityOptions().find((option) => option.value === priority) ?? null}
                  isClearable={false}
                  testId="work-item-create-priority"
                  onChange={(option) =>
                    option && setPriority((option as { value: number }).value)
                  }
                />
              </FormField>
              <FormField label={t("create.plannedStart")} htmlFor="wi-planned-start">
                <DatePicker
                  id="wi-planned-start"
                  value={plannedStart}
                  placeholder={t("create.datePlaceholder")}
                  testId="work-item-create-planned-start"
                  onChange={setPlannedStart}
                />
              </FormField>
              <FormField label={t("create.plannedEnd")} htmlFor="wi-planned-end">
                <DatePicker
                  id="wi-planned-end"
                  value={plannedEnd}
                  placeholder={t("create.datePlaceholder")}
                  testId="work-item-create-planned-end"
                  onChange={setPlannedEnd}
                />
              </FormField>
              {parentKinds.length > 0 && (
                <FormField label={t("create.parent")}>
                  <WorkItemPicker
                    projectKey={projectKey}
                    allowedKinds={parentKinds}
                    value={parent}
                    onChange={setParent}
                    placeholder={t("create.parentPlaceholder")}
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
                assigneeLabel={t("create.assignee")}
              />
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="work-item-create-cancel">
              {t("actions.cancel")}
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              testId="work-item-create-submit"
              onClick={() => void submit()}
            >
              {t("actions.create")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
