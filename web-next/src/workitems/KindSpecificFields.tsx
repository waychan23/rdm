import { Box, Stack } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { portalMenuProps } from "../lib/portalMenu";
import { SEVERITY_OPTIONS, TASK_TYPE_OPTIONS } from "./constants";

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
  est_work_hours: number;
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
}: Props) {
  if (kind === "story") {
    return (
      <FormField label="验收标准（Markdown）">
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
        <FormField label="严重度" htmlFor="wi-severity">
          <Select
            {...portalMenuProps}
            inputId="wi-severity"
            options={SEVERITY_OPTIONS}
            value={SEVERITY_OPTIONS.find((o) => o.value === issue.severity)}
            onChange={(opt) =>
              opt && onIssue({ ...issue, severity: (opt as { value: string }).value })
            }
          />
        </FormField>
        <FormField label="环境" htmlFor="wi-environment">
          <Textfield
            id="wi-environment"
            value={issue.environment}
            testId="wi-environment"
            onChange={(e) => onIssue({ ...issue, environment: e.currentTarget.value })}
          />
        </FormField>
        <FormField label="来源 story">
          <WorkItemPicker
            projectKey={projectKey}
            allowedKinds={["story"]}
            value={issue.sourceStory}
            onChange={(option) => onIssue({ ...issue, sourceStory: option })}
            placeholder="选择来源 story（可清除）"
            testId="wi-source-story"
          />
        </FormField>
        <FormField label="复现步骤（Markdown）">
          <MarkdownEditor
            value={issue.repro}
            onChange={(v) => onIssue({ ...issue, repro: v })}
            projectKey={projectKey}
            minimumRows={3}
            testId="wi-repro"
          />
        </FormField>
        <FormField label="期望行为（Markdown）">
          <MarkdownEditor
            value={issue.expected}
            onChange={(v) => onIssue({ ...issue, expected: v })}
            projectKey={projectKey}
            minimumRows={2}
            testId="wi-expected"
          />
        </FormField>
        <FormField label="实际行为（Markdown）">
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
        <FormField label="任务类型" htmlFor="wi-task-type">
          <Select
            {...portalMenuProps}
            inputId="wi-task-type"
            options={TASK_TYPE_OPTIONS}
            value={TASK_TYPE_OPTIONS.find((o) => o.value === task.task_type)}
            onChange={(opt) =>
              opt && onTask({ ...task, task_type: (opt as { value: string }).value })
            }
          />
        </FormField>
        <FormField label="预估工时（h）" htmlFor="wi-est-hours">
          <Textfield
            id="wi-est-hours"
            type="number"
            min={0}
            step={0.5}
            value={task.est_work_hours}
            testId="wi-est-hours"
            onChange={(e) => onTask({ ...task, est_work_hours: Number(e.currentTarget.value) })}
          />
        </FormField>
      </Stack>
    );
  }
  return <Box />;
}
