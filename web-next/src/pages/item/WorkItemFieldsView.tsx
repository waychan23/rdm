import { Stack, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import TextButton from "../../components/TextButton";
import type { MarkdownImageClick } from "../../components/MarkdownText";
import type { WorkItem } from "../../types";
import { severityOptions } from "../../workitems/constants";
import {
  InlineChoiceField,
  InlineMarkdownField,
  InlineTextField,
} from "./InlineFields";

function Empty() {
  const { t } = useTranslation("item");
  return (
    <Text size="small" color="color.text.subtlest">
      {t("fieldsView.empty")}
    </Text>
  );
}

/** Blank text clears the field instead of storing whitespace. */
function blankToNull(value: string): string | null {
  return value.trim() ? value : null;
}

const hoursText = (value: string) => (value.trim() ? `${value}h` : "—");

interface Props {
  item: WorkItem;
  projectKey: string;
  canEdit: boolean;
  requiredFields?: ReadonlySet<string>;
  onPatch: (payload: Record<string, unknown>) => Promise<boolean>;
  onOpenItem: (id: string) => void;
  onImageClick: (image: MarkdownImageClick) => void;
}

/**
 * Kind-specific fields. Each value edits in place and PATCHes only its own
 * top-level key (flat schema, see docs/web-next-ui.md §6.3).
 */
export default function WorkItemFieldsView({
  item,
  projectKey,
  canEdit,
  requiredFields,
  onPatch,
  onOpenItem,
  onImageClick,
}: Props) {
  const { t } = useTranslation("item");
  const fields = (item.fields ?? {}) as Record<string, unknown>;
  const isRequired = (key: string) => Boolean(requiredFields?.has(key));
  if (item.kind === "epic" || Object.keys(fields).length === 0) {
    return (
      <Text size="small" color="color.text.subtlest">
        {t("fieldsView.noFields")}
      </Text>
    );
  }

  if (item.kind === "story") {
    return (
      <InlineMarkdownField
        testId="item-acceptance"
        label={t("fieldsView.acceptance")}
        required={isRequired("acceptance_criteria_md")}
        value={fields.acceptance_criteria_md as string | undefined}
        canEdit={canEdit}
        projectKey={projectKey}
        emptyText={t("fieldsView.empty")}
        placeholder={t("fieldsView.acceptancePlaceholder")}
        minimumRows={3}
        editLabel={t("fieldsView.editAcceptance")}
        onImageClick={onImageClick}
        onSave={(next) => onPatch({ acceptance_criteria_md: blankToNull(next) })}
      />
    );
  }

  if (item.kind === "issue") {
    const sourceStoryId = fields.source_story_id as string | undefined;
    return (
      <Stack space="space.150">
        <InlineChoiceField
          testId="item-severity"
          label={t("fieldsView.severity")}
          required={isRequired("severity")}
          value={String(fields.severity ?? "major")}
          options={severityOptions()}
          canEdit={canEdit}
          editLabel={t("fieldsView.editSeverity")}
          onSave={(next) => onPatch({ severity: next })}
        />
        <InlineTextField
          testId="item-environment"
          label={t("fieldsView.environment")}
          required={isRequired("environment")}
          value={String(fields.environment ?? "")}
          canEdit={canEdit}
          emptyText={t("fieldsView.empty")}
          editLabel={t("fieldsView.editEnvironment")}
          onSave={(next) => onPatch({ environment: blankToNull(next) })}
        />
        <div className="rdm-inline-field" data-testid="item-source-story">
          <div className="rdm-item-section-label">{t("fieldsView.sourceStory")}</div>
          {sourceStoryId ? (
            <TextButton onClick={() => onOpenItem(sourceStoryId)}>
              {sourceStoryId}
            </TextButton>
          ) : (
            <Empty />
          )}
        </div>
        {(
          [
            ["repro_steps_md", t("fieldsView.repro")],
            ["expected_behavior_md", t("fieldsView.expected")],
            ["actual_behavior_md", t("fieldsView.actual")],
          ] as const
        ).map(([key, label]) => (
          <InlineMarkdownField
            key={key}
            testId={`item-${key}`}
            label={label}
            required={isRequired(key)}
            value={fields[key] as string | undefined}
            canEdit={canEdit}
            projectKey={projectKey}
            emptyText={t("fieldsView.empty")}
            placeholder={t("fieldsView.fillPlaceholder", { label })}
            minimumRows={3}
            editLabel={t("fieldsView.editLabel", { label })}
            onImageClick={onImageClick}
            onSave={(next) => onPatch({ [key]: blankToNull(next) })}
          />
        ))}
      </Stack>
    );
  }

  return (
    <Stack space="space.150">
      <InlineTextField
        testId="item-est-work-hours"
        label={t("fieldsView.estHours")}
        required={isRequired("est_work_hours")}
        value={fields.est_work_hours === null || fields.est_work_hours === undefined
          ? ""
          : String(fields.est_work_hours)}
        canEdit={canEdit}
        emptyText="—"
        inputType="number"
        editLabel={t("fieldsView.editEstHours")}
        renderView={hoursText}
        onSave={(next) =>
          onPatch({ est_work_hours: next.trim() === "" ? null : Number(next) })
        }
      />
      <InlineTextField
        testId="item-actual-work-hours"
        label={t("fieldsView.actualHours")}
        required={isRequired("actual_work_hours")}
        value={fields.actual_work_hours === null || fields.actual_work_hours === undefined
          ? ""
          : String(fields.actual_work_hours)}
        canEdit={canEdit}
        emptyText="—"
        inputType="number"
        editLabel={t("fieldsView.editActualHours")}
        renderView={hoursText}
        onSave={(next) =>
          onPatch({ actual_work_hours: next.trim() === "" ? null : Number(next) })
        }
      />
      <InlineTextField
        testId="item-code-branch"
        label={t("fieldsView.codeBranch")}
        required={isRequired("code_branch")}
        value={String(fields.code_branch ?? "")}
        canEdit={canEdit}
        emptyText={t("fieldsView.empty")}
        editLabel={t("fieldsView.editCodeBranch")}
        onSave={(next) => onPatch({ code_branch: blankToNull(next) })}
      />
    </Stack>
  );
}
