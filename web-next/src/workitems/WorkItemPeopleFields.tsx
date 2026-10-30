import { useEffect, useState } from "react";

import { Stack } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";

import FormField from "../components/FormField";
import MarkdownEditor from "../components/MarkdownEditor";
import { api } from "../lib/api";
import { flattenMembers } from "../lib/members";
import { portalMenuProps } from "../lib/portalMenu";
import type { OrgUser, ProjectMemberRow, WorkflowFields } from "../types";

export interface OptionalFieldValues {
  assignee: string | null;
  participants: string[];
  reviewer: string[];
  reviewContent: string;
  custom: Record<string, unknown>;
}

export const emptyOptionalValues = (assignee: string | null = null): OptionalFieldValues => ({
  assignee,
  participants: [],
  reviewer: [],
  reviewContent: "",
  custom: {},
});

interface Props {
  projectKey: string;
  fields: WorkflowFields;
  value: OptionalFieldValues;
  onChange: (value: OptionalFieldValues) => void;
  showAssignee?: boolean;
  assigneeLabel?: string;
}

export default function WorkItemPeopleFields({
  projectKey,
  fields,
  value,
  onChange,
  showAssignee = false,
  assigneeLabel = "负责人",
}: Props) {
  const [members, setMembers] = useState<OrgUser[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)
      .then((res) => {
        if (!cancelled) setMembers(flattenMembers(res.data));
      })
      .catch(() => {
        if (!cancelled) setMembers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectKey]);

  const options = members.map((member) => ({
    label: `${member.name}${member.type === "agent" ? "（agent）" : ""}`,
    value: member.id,
  }));
  const patch = (next: Partial<OptionalFieldValues>) =>
    onChange({ ...value, ...next });

  const setCustom = (key: string, raw: unknown) =>
    onChange({ ...value, custom: { ...value.custom, [key]: raw } });

  return (
    <Stack space="space.150">
      {showAssignee && (
        <FormField label={assigneeLabel}>
          <Select
            {...portalMenuProps}
            isClearable
            options={options}
            value={options.find((option) => option.value === value.assignee) ?? null}
            placeholder="选择负责人"
            testId="wi-assignee"
            onChange={(option) =>
              patch({ assignee: (option as { value: string } | null)?.value ?? null })
            }
          />
        </FormField>
      )}
      <FormField label="参与人（可多选）">
        <Select
          {...portalMenuProps}
          isMulti
          options={options}
          value={options.filter((option) => value.participants.includes(option.value))}
          placeholder="选择参与人"
          testId="wi-participants"
          onChange={(selected) =>
            patch({
              participants: Array.from(selected ?? []).map((option) => option.value),
            })
          }
        />
      </FormField>
      {fields.reviewer && (
        <FormField label="评审人（可多选）">
          <Select
            {...portalMenuProps}
            isMulti
            options={options}
            value={options.filter((option) => value.reviewer.includes(option.value))}
            placeholder="选择评审人"
            testId="wi-reviewer"
            onChange={(selected) =>
              patch({
                reviewer: Array.from(selected ?? []).map((option) => option.value),
              })
            }
          />
        </FormField>
      )}
      {fields.review_content && (
        <FormField label="评审意见（Markdown）">
          <MarkdownEditor
            value={value.reviewContent}
            onChange={(reviewContent) => patch({ reviewContent })}
            projectKey={projectKey}
            minimumRows={3}
            testId="wi-review-content"
          />
        </FormField>
      )}
      {fields.custom.map((field) => {
        const raw = value.custom[field.key];
        if (field.type === "text") {
          return (
            <FormField key={field.key} label={field.label}>
              <MarkdownEditor
                value={typeof raw === "string" ? raw : ""}
                onChange={(next) => setCustom(field.key, next)}
                projectKey={projectKey}
                minimumRows={2}
                testId={`wi-custom-${field.key}`}
              />
            </FormField>
          );
        }
        if (field.type === "number") {
          return (
            <FormField key={field.key} label={field.label}>
              <Textfield
                type="number"
                value={raw === null || raw === undefined ? "" : String(raw)}
                testId={`wi-custom-${field.key}`}
                onChange={(event) =>
                  setCustom(
                    field.key,
                    event.currentTarget.value === ""
                      ? null
                      : Number(event.currentTarget.value),
                  )
                }
              />
            </FormField>
          );
        }
        const selected = Array.isArray(raw)
          ? raw.map(String)
          : raw === null || raw === undefined || raw === ""
            ? []
            : [String(raw)];
        return (
          <FormField key={field.key} label={field.label}>
            <Select
              {...portalMenuProps}
              isMulti={field.multiple}
              isClearable
              options={options}
              value={
                field.multiple
                  ? options.filter((option) => selected.includes(option.value))
                  : options.find((option) => option.value === selected[0]) ?? null
              }
              placeholder="选择成员"
              testId={`wi-custom-${field.key}`}
              onChange={(choice) => {
                if (field.multiple) {
                  const many = (
                    Array.isArray(choice) ? [...choice] : choice ? [choice] : []
                  ) as { value: string }[];
                  setCustom(
                    field.key,
                    many.map((option) => option.value),
                  );
                } else {
                  const option = choice as { value: string } | null;
                  setCustom(field.key, option ? [option.value] : []);
                }
              }}
            />
          </FormField>
        );
      })}
    </Stack>
  );
}
