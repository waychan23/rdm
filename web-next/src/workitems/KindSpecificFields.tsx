import type { CSSProperties } from "react";

import { Box, Stack } from "@atlaskit/primitives";
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";
import Select from "@atlaskit/select";

import { SEVERITY_OPTIONS, TASK_TYPE_OPTIONS } from "./constants";

export interface IssueFields {
  severity: string;
  environment: string;
  repro: string;
}

export interface TaskFields {
  task_type: string;
  est_work_hours: number;
}

interface Props {
  kind: string;
  acceptance: string;
  onAcceptance: (v: string) => void;
  issue: IssueFields;
  onIssue: (v: IssueFields) => void;
  task: TaskFields;
  onTask: (v: TaskFields) => void;
}

const fieldLabel: CSSProperties = {
  display: "block",
  fontWeight: "var(--ds-font-weight-medium, 500)",
  marginBottom: 4,
};

// Kind-specific inputs shared by the create and edit dialogs.
export default function KindSpecificFields({
  kind,
  acceptance,
  onAcceptance,
  issue,
  onIssue,
  task,
  onTask,
}: Props) {
  if (kind === "story") {
    return (
      <Stack space="space.050">
        <label htmlFor="wi-acceptance" style={fieldLabel}>
          验收标准（Markdown）
        </label>
        <TextArea
          id="wi-acceptance"
          value={acceptance}
          minimumRows={3}
          onChange={(e) => onAcceptance(e.currentTarget.value)}
        />
      </Stack>
    );
  }
  if (kind === "issue") {
    return (
      <Stack space="space.150">
        <Stack space="space.050">
          <label htmlFor="wi-severity" style={fieldLabel}>
            严重度
          </label>
          <Select
            inputId="wi-severity"
            options={SEVERITY_OPTIONS}
            value={SEVERITY_OPTIONS.find((o) => o.value === issue.severity)}
            onChange={(opt) => opt && onIssue({ ...issue, severity: (opt as { value: string }).value })}
          />
        </Stack>
        <Stack space="space.050">
          <label htmlFor="wi-environment" style={fieldLabel}>
            环境
          </label>
          <Textfield
            id="wi-environment"
            value={issue.environment}
            onChange={(e) => onIssue({ ...issue, environment: e.currentTarget.value })}
          />
        </Stack>
        <Stack space="space.050">
          <label htmlFor="wi-repro" style={fieldLabel}>
            复现步骤（Markdown）
          </label>
          <TextArea
            id="wi-repro"
            value={issue.repro}
            minimumRows={3}
            onChange={(e) => onIssue({ ...issue, repro: e.currentTarget.value })}
          />
        </Stack>
      </Stack>
    );
  }
  if (kind === "task") {
    return (
      <Stack space="space.150">
        <Stack space="space.050">
          <label htmlFor="wi-task-type" style={fieldLabel}>
            任务类型
          </label>
          <Select
            inputId="wi-task-type"
            options={TASK_TYPE_OPTIONS}
            value={TASK_TYPE_OPTIONS.find((o) => o.value === task.task_type)}
            onChange={(opt) => opt && onTask({ ...task, task_type: (opt as { value: string }).value })}
          />
        </Stack>
        <Stack space="space.050">
          <label htmlFor="wi-est-hours" style={fieldLabel}>
            预估工时（h）
          </label>
          <Textfield
            id="wi-est-hours"
            type="number"
            min={0}
            step={0.5}
            value={task.est_work_hours}
            onChange={(e) => onTask({ ...task, est_work_hours: Number(e.currentTarget.value) })}
          />
        </Stack>
      </Stack>
    );
  }
  return <Box />;
}
