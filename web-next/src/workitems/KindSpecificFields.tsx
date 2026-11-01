import { Box, Stack } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { useTranslation } from "react-i18next";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { sanitizeHoursInput } from "../lib/format";
import { portalMenuProps } from "../lib/portalMenu";
import { severityOptions, taskTypeOptions } from "./constants";

export interface IssueFields {
  severity: string;
  environment: string;
  repro: string;
  expected: string;
  actual: string;
  sourceStory: WorkItemOption | null;
}

export interface TaskFields {
  task_type: string;
  /** Raw input text so "0." and leading zeros are not lost while typing. */
  est_work_hours: string;
}

interface Props {
  kind: string;
  projectKey: string;
  acceptance: string;
  onAcceptance: (v: string) => void;
  issue: IssueFields;
  onIssue: (v: IssueFields) => void;
  task: TaskFields;
  onTask: (v: TaskFields) => void;
  taskTypeLocked?: boolean;
  /** The create form renders the task type above the title itself. */
  hideTaskType?: boolean;
}

// Kind-specific inputs shared by the create and edit dialogs.
export default function KindSpecificFields({
  kind,
  projectKey,
  acceptance,
  onAcceptance,
  issue,
  onIssue,
  task,
  onTask,
  taskTypeLocked = false,
  hideTaskType = false,
}: Props) {
  const { t } = useTranslation("workitems");
  if (kind === "story") {
    return (
      <FormField label={t("kind.acceptance")}>
        <MarkdownEditor
          value={acceptance}
          onChange={onAcceptance}
          projectKey={projectKey}
          minimumRows={3}
          testId="wi-acceptance"
        />
      </FormField>
    );
  }
  if (kind === "issue") {
    return (
      <Stack space="space.150">
        <FormField label={t("kind.severity")} htmlFor="wi-severity">
          <Select
            {...portalMenuProps}
            inputId="wi-severity"
            options={severityOptions()}
            value={severityOptions().find((o) => o.value === issue.severity)}
            onChange={(opt) =>
              opt && onIssue({ ...issue, severity: (opt as { value: string }).value })
            }
          />
        </FormField>
        <FormField label={t("kind.environment")} htmlFor="wi-environment">
          <Textfield
            id="wi-environment"
            value={issue.environment}
            testId="wi-environment"
            onChange={(e) => onIssue({ ...issue, environment: e.currentTarget.value })}
          />
        </FormField>
        <FormField label={t("kind.sourceStory")}>
          <WorkItemPicker
            projectKey={projectKey}
            allowedKinds={["story"]}
            value={issue.sourceStory}
            onChange={(option) => onIssue({ ...issue, sourceStory: option })}
            placeholder={t("kind.sourceStoryPlaceholder")}
            testId="wi-source-story"
          />
        </FormField>
        <FormField label={t("kind.repro")}>
          <MarkdownEditor
            value={issue.repro}
            onChange={(v) => onIssue({ ...issue, repro: v })}
            projectKey={projectKey}
            minimumRows={3}
            testId="wi-repro"
          />
        </FormField>
        <FormField label={t("kind.expected")}>
          <MarkdownEditor
            value={issue.expected}
            onChange={(v) => onIssue({ ...issue, expected: v })}
            projectKey={projectKey}
            minimumRows={2}
            testId="wi-expected"
          />
        </FormField>
        <FormField label={t("kind.actual")}>
          <MarkdownEditor
            value={issue.actual}
            onChange={(v) => onIssue({ ...issue, actual: v })}
            projectKey={projectKey}
            minimumRows={2}
            testId="wi-actual"
          />
        </FormField>
      </Stack>
    );
  }
  if (kind === "task") {
    return (
      <Stack space="space.150">
        {!hideTaskType && (
          <FormField label={t("kind.taskType")} htmlFor="wi-task-type">
            <Select
              {...portalMenuProps}
              inputId="wi-task-type"
              options={taskTypeOptions()}
              value={taskTypeOptions().find((o) => o.value === task.task_type)}
              isDisabled={taskTypeLocked}
              onChange={(opt) =>
                opt && onTask({ ...task, task_type: (opt as { value: string }).value })
              }
            />
          </FormField>
        )}
        <FormField label={t("kind.estHours")} htmlFor="wi-est-hours">
          <Textfield
            id="wi-est-hours"
            type="text"
            inputMode="decimal"
            value={task.est_work_hours}
            testId="wi-est-hours"
            onChange={(e) =>
              onTask({
                ...task,
                est_work_hours: sanitizeHoursInput(e.currentTarget.value),
              })
            }
          />
        </FormField>
      </Stack>
    );
  }
  return <Box />;
}
