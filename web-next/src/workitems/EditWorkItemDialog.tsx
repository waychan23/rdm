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
import { Stack } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { useTranslation } from "react-i18next";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { reparentWorkItem, updateWorkItem } from "../api/work-items-api";
import { getWorkflow } from "../api/workflow-api";
import { errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import { parseHoursInput } from "../lib/format";
import { portalMenuProps } from "../lib/portalMenu";
import type { WorkflowDto, WorkflowFields, WorkItem } from "../types";
import { allowedParentKinds } from "./parentRules";
import { DEFAULT_PRIORITY, priorityOptions, priorityOption } from "./priority";
import KindSpecificFields, { type IssueFields, type TaskFields } from "./KindSpecificFields";
import WorkItemPeopleFields, {
  emptyOptionalValues,
  type OptionalFieldValues,
} from "./WorkItemPeopleFields";

interface Props {
  open: boolean;
  projectKey: string;
  item: WorkItem | null;
  parentOption?: WorkItemOption | null;
  onClose: () => void;
  onSaved: (item: WorkItem) => void;
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

export default function EditWorkItemDialog({
  open,
  projectKey,
  item,
  parentOption = null,
  onClose,
  onSaved,
}: Props) {
  const { t } = useTranslation("workitems");
  const notify = useNotify();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(DEFAULT_PRIORITY);
  const [plannedStart, setPlannedStart] = useState("");
  const [plannedEnd, setPlannedEnd] = useState("");
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
  const [task, setTask] = useState<TaskFields>({ task_type: "other", est_work_hours: "0" });
  const [workflow, setWorkflow] = useState<WorkflowDto | null>(null);
  const [people, setPeople] = useState<OptionalFieldValues>(emptyOptionalValues(null));
  const [saving, setSaving] = useState(false);
  const fields = useMemo(
    () =>
      resolveFields(
        workflow,
        item?.kind ?? "",
        item?.task_type ?? task.task_type,
      ),
    [workflow, item?.kind, item?.task_type, task.task_type],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getWorkflow(projectKey)
      .then((workflow) => {
        if (!cancelled) setWorkflow(workflow);
      })
      .catch(() => {
        if (!cancelled) setWorkflow(null);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectKey]);

  useEffect(() => {
    if (!open || !item) return;
    setTitle(item.title);
    setDescription(item.description_md ?? "");
    setPriority(priorityOption(item.priority).value);
    setPlannedStart(item.planned_start_date ?? "");
    setPlannedEnd(item.planned_end_date ?? "");
    setParent(parentOption);
    setPeople({
      assignee: item.assignee?.id ?? null,
      participants: (item.participants ?? []).map((member) => member.id),
      reviewer: (item.reviewer ?? []).map((member) => member.id),
      reviewContent: item.review_content_md ?? "",
      custom: { ...(item.custom_fields ?? {}) },
    });
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
      est_work_hours:
        f.est_work_hours === null || f.est_work_hours === undefined
          ? "0"
          : String(f.est_work_hours),
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
        planned_start_date: plannedStart || null,
        planned_end_date: plannedEnd || null,
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
        payload.est_work_hours = parseHoursInput(task.est_work_hours);
      }
      payload.participants = people.participants;
      if (fields.reviewer) payload.reviewer = people.reviewer;
      if (fields.review_content) {
        payload.review_content_md = people.reviewContent.trim()
          ? people.reviewContent
          : null;
      }
      if (fields.custom.length > 0) {
        payload.custom_fields = Object.fromEntries(
          fields.custom.map((field) => [field.key, people.custom[field.key] ?? null]),
        );
      }
      let updated = (
        await updateWorkItem(item.display_id, payload)
      );

      const wantedParent = parent?.display_id ?? null;
      const currentParent = parentOption?.display_id ?? null;
      if (wantedParent !== currentParent) {
        updated = (
          await reparentWorkItem(item.display_id, wantedParent, updated.row_version)
        );
      }
      notify.success(t("edit.saved"));
      onSaved(updated);
      onClose();
    } catch (e) {
      notify.error(t("edit.saveFailed"), errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  const parentKinds = item ? allowedParentKinds(item.kind) : [];

  return (
    <ModalTransition>
      {open && item && (
        <ModalDialog
          onClose={onClose}
          width="680px"
          // Backdrop clicks must not discard a half-filled form (RDM-163).
          shouldCloseOnOverlayClick={false}
          testId="work-item-edit-dialog"
        >
          <ModalHeader>
            <ModalTitle>{t("edit.title")}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label={t("edit.titleLabel")} htmlFor="wi-edit-title">
                <Textfield
                  id="wi-edit-title"
                  value={title}
                  testId="work-item-edit-title"
                  onChange={(e) => setTitle(e.currentTarget.value)}
                />
              </FormField>
              <FormField label={t("edit.description")}>
                <MarkdownEditor
                  value={description}
                  onChange={setDescription}
                  projectKey={projectKey}
                  minimumRows={4}
                  testId="work-item-edit-description"
                />
              </FormField>
              <FormField label={t("edit.priority")} htmlFor="wi-edit-priority">
                <Select
                  {...portalMenuProps}
                  inputId="wi-edit-priority"
                  options={priorityOptions()}
                  value={priorityOptions().find((option) => option.value === priority) ?? null}
                  isClearable={false}
                  testId="work-item-edit-priority"
                  onChange={(option) =>
                    option && setPriority((option as { value: number }).value)
                  }
                />
              </FormField>
              <FormField label={t("edit.plannedStart")} htmlFor="wi-edit-planned-start">
                <DatePicker
                  id="wi-edit-planned-start"
                  value={plannedStart}
                  placeholder={t("edit.datePlaceholder")}
                  testId="work-item-edit-planned-start"
                  onChange={setPlannedStart}
                />
              </FormField>
              <FormField label={t("edit.plannedEnd")} htmlFor="wi-edit-planned-end">
                <DatePicker
                  id="wi-edit-planned-end"
                  value={plannedEnd}
                  placeholder={t("edit.datePlaceholder")}
                  testId="work-item-edit-planned-end"
                  onChange={setPlannedEnd}
                />
              </FormField>
              {parentKinds.length > 0 && (
                <FormField label={t("edit.parent")}>
                  <WorkItemPicker
                    projectKey={projectKey}
                    allowedKinds={parentKinds}
                    excludeIds={[item.id]}
                    value={parent}
                    onChange={setParent}
                    placeholder={t("edit.parentPlaceholder")}
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
                taskTypeLocked={item.kind === "task"}
              />
              <WorkItemPeopleFields
                projectKey={projectKey}
                fields={fields}
                value={people}
                onChange={setPeople}
              />
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="work-item-edit-cancel">
              {t("actions.cancel")}
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              testId="work-item-edit-submit"
              onClick={() => void save()}
            >
              {t("actions.save")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
