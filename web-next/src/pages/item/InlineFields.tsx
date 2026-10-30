import { useRef, useState } from "react";
import type { MouseEvent, ReactNode } from "react";

import Button from "@atlaskit/button/default/button";
import InlineEdit from "@atlaskit/inline-edit";
import { Inline, Text } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";

import MarkdownEditor from "../../components/MarkdownEditor";
import MarkdownText, { type MarkdownImageClick } from "../../components/MarkdownText";
import PersonCell from "../../components/PersonCell";
import { portalMenuProps } from "../../lib/portalMenu";

/**
 * Field-level editing on the work-item detail panel.
 *
 * Every field edits in place through ADS `InlineEdit`: the read view is
 * clickable (and keyboard-focusable through the inline edit button), the edit
 * view shows its own 保存/取消 actions, and a failed save keeps the editor
 * open so the draft is not lost. The panel never PATCHes the whole item — each
 * field sends just its own payload.
 */

export interface MemberOption {
  label: string;
  value: string;
  name: string;
}

/** Let clicks on links/images inside markdown read views keep their own behaviour. */
function stopInteractiveClick(event: MouseEvent<HTMLDivElement>) {
  const target = event.target as HTMLElement | null;
  if (target?.closest("a, img, button, input, textarea, select")) {
    event.stopPropagation();
  }
}

function FieldShell({
  label,
  testId,
  children,
}: {
  label?: ReactNode;
  testId: string;
  children: ReactNode;
}) {
  return (
    <div className="rdm-inline-field" data-testid={testId}>
      {label ? <div className="rdm-item-section-label">{label}</div> : null}
      {children}
    </div>
  );
}

function EditorShell({ children }: { children: ReactNode }) {
  return (
    <div
      className="rdm-inline-editor"
      // The panel closes on Escape; prevent that while a field editor is open.
      // InlineEdit's own form handler still cancels the edit view.
      onKeyDownCapture={(event) => {
        if (event.key === "Escape") event.preventDefault();
      }}
    >
      {children}
    </div>
  );
}

function EditorFooter({
  errorMessage,
  saving,
  testId,
  onCancel,
}: {
  errorMessage?: string;
  saving: boolean;
  testId: string;
  onCancel: () => void;
}) {
  return (
    <div className="rdm-inline-foot">
      {errorMessage ? (
        <Text size="small" color="color.text.danger">
          {errorMessage}
        </Text>
      ) : null}
      <div className="rdm-inline-actions">
        <Button
          type="submit"
          appearance="primary"
          spacing="compact"
          isLoading={saving}
          testId={`${testId}-save`}
        >
          保存
        </Button>
        <Button
          type="button"
          appearance="subtle"
          spacing="compact"
          isDisabled={saving}
          testId={`${testId}-cancel`}
          onClick={onCancel}
        >
          取消
        </Button>
      </div>
    </div>
  );
}

function useInlineSave<T>(
  onSave: (value: T) => Promise<boolean>,
  done: () => void,
): { saving: boolean; confirm: (value: T) => void; cancel: () => void } {
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);

  const confirm = (value: T) => {
    if (busy.current) return;
    busy.current = true;
    setSaving(true);
    void (async () => {
      try {
        if (await onSave(value)) done();
      } catch {
        // The caller reports the failure; keep the draft open for a retry.
      } finally {
        busy.current = false;
        setSaving(false);
      }
    })();
  };

  const cancel = () => {
    if (busy.current) return;
    done();
  };

  return { saving, confirm, cancel };
}

// --- markdown fields (description, review content, kind-specific long text) ---

interface InlineMarkdownFieldProps {
  testId: string;
  label?: ReactNode;
  value: string | null | undefined;
  canEdit: boolean;
  projectKey: string;
  emptyText?: string;
  placeholder?: string;
  minimumRows?: number;
  editLabel: string;
  readClassName?: string;
  onSave: (next: string) => Promise<boolean>;
  onImageClick?: (image: MarkdownImageClick) => void;
}

export function InlineMarkdownField({
  testId,
  label,
  value,
  canEdit,
  projectKey,
  emptyText = "未填写",
  placeholder,
  minimumRows = 3,
  editLabel,
  readClassName,
  onSave,
  onImageClick,
}: InlineMarkdownFieldProps) {
  const [editing, setEditing] = useState(false);
  const { saving, confirm, cancel } = useInlineSave(onSave, () => setEditing(false));
  const committed = value ?? "";
  const readClass = readClassName
    ? `rdm-inline-read ${readClassName}`
    : "rdm-inline-read";

  const view = (
    <div className={readClass} onClick={stopInteractiveClick}>
      {committed.trim() ? (
        <MarkdownText source={committed} onImageClick={onImageClick} />
      ) : (
        <Text size="small" color="color.text.subtlest">
          {emptyText}
        </Text>
      )}
    </div>
  );

  return (
    <FieldShell label={label} testId={testId}>
      {canEdit ? (
        <InlineEdit<string>
          testId={testId}
          editButtonLabel={editLabel}
          isEditing={editing}
          defaultValue={committed}
          keepEditViewOpenOnBlur
          hideActionButtons
          readViewFitContainerWidth
          onEdit={() => setEditing(true)}
          onCancel={cancel}
          onConfirm={confirm}
          readView={() => view}
          editView={(fieldProps) => (
            <EditorShell>
              <MarkdownEditor
                value={String(fieldProps.value ?? "")}
                onChange={(next) => fieldProps.onChange(next)}
                projectKey={projectKey}
                placeholder={placeholder}
                minimumRows={minimumRows}
                autoFocus
                isDisabled={saving}
                testId={`${testId}-input`}
                onImageClick={onImageClick}
                onSubmit={() => confirm(String(fieldProps.value ?? ""))}
              />
              <EditorFooter
                errorMessage={fieldProps.errorMessage}
                saving={saving}
                testId={testId}
                onCancel={cancel}
              />
            </EditorShell>
          )}
        />
      ) : (
        view
      )}
    </FieldShell>
  );
}

// --- single-line text / number fields ---

interface InlineTextFieldProps {
  testId: string;
  label?: ReactNode;
  value: string;
  canEdit: boolean;
  emptyText?: string;
  placeholder?: string;
  editLabel: string;
  inputType?: "text" | "number";
  maxLength?: number;
  readClassName?: string;
  validate?: (value: string) => string | undefined;
  renderView?: (value: string) => ReactNode;
  onSave: (next: string) => Promise<boolean>;
}

export function InlineTextField({
  testId,
  label,
  value,
  canEdit,
  emptyText = "未填写",
  placeholder,
  editLabel,
  inputType = "text",
  maxLength,
  readClassName,
  validate,
  renderView,
  onSave,
}: InlineTextFieldProps) {
  const [editing, setEditing] = useState(false);
  const { saving, confirm, cancel } = useInlineSave(onSave, () => setEditing(false));

  const view = (
    <div
      className={readClassName ? `rdm-inline-read ${readClassName}` : "rdm-inline-read"}
    >
      {renderView ? (
        renderView(value)
      ) : value ? (
        <Text size="small">{value}</Text>
      ) : (
        <Text size="small" color="color.text.subtlest">
          {emptyText}
        </Text>
      )}
    </div>
  );

  const check = (raw: unknown) => {
    const text = String(raw ?? "");
    if (inputType === "number" && text.trim() !== "" && Number.isNaN(Number(text))) {
      return "请输入数字";
    }
    return validate?.(text);
  };

  return (
    <FieldShell label={label} testId={testId}>
      {canEdit ? (
        <InlineEdit<string>
          testId={testId}
          editButtonLabel={editLabel}
          isEditing={editing}
          defaultValue={value}
          keepEditViewOpenOnBlur
          hideActionButtons
          readViewFitContainerWidth
          validate={check}
          onEdit={() => setEditing(true)}
          onCancel={cancel}
          onConfirm={confirm}
          readView={() => view}
          editView={(fieldProps) => (
            <EditorShell>
              <Textfield
                value={String(fieldProps.value ?? "")}
                type={inputType}
                maxLength={maxLength}
                placeholder={placeholder}
                autoFocus
                isDisabled={saving}
                testId={`${testId}-input`}
                onChange={(event) => fieldProps.onChange(event.currentTarget.value)}
              />
              <EditorFooter
                errorMessage={fieldProps.errorMessage}
                saving={saving}
                testId={testId}
                onCancel={cancel}
              />
            </EditorShell>
          )}
        />
      ) : (
        view
      )}
    </FieldShell>
  );
}

// --- member fields (assignee, participants, reviewer, custom user fields) ---

interface InlineMemberFieldProps {
  testId: string;
  label?: ReactNode;
  canEdit: boolean;
  multiple: boolean;
  ids: string[];
  options: MemberOption[];
  emptyText: string;
  placeholder: string;
  editLabel: string;
  onSave: (ids: string[]) => Promise<boolean>;
}

export function InlineMemberField({
  testId,
  label,
  canEdit,
  multiple,
  ids,
  options,
  emptyText,
  placeholder,
  editLabel,
  onSave,
}: InlineMemberFieldProps) {
  const [editing, setEditing] = useState(false);
  const { saving, confirm, cancel } = useInlineSave(onSave, () => setEditing(false));
  const nameById = new Map(options.map((option) => [option.value, option.name]));

  const view = (
    <div className="rdm-inline-read">
      {ids.length === 0 ? (
        <Text size="small" color="color.text.subtlest">
          {emptyText}
        </Text>
      ) : (
        <Inline space="space.100" shouldWrap>
          {ids.map((id) => (
            <PersonCell key={id} name={nameById.get(id) ?? id} />
          ))}
        </Inline>
      )}
    </div>
  );

  return (
    <FieldShell label={label} testId={testId}>
      {canEdit ? (
        <InlineEdit<string[]>
          testId={testId}
          editButtonLabel={editLabel}
          isEditing={editing}
          defaultValue={ids}
          keepEditViewOpenOnBlur
          hideActionButtons
          readViewFitContainerWidth
          validate={(raw) => {
            const selected = Array.isArray(raw) ? raw : [];
            return !multiple && selected.length === 0 ? "请选择成员" : undefined;
          }}
          onEdit={() => setEditing(true)}
          onCancel={cancel}
          onConfirm={confirm}
          readView={() => view}
          editView={(fieldProps) => {
            const selected = Array.isArray(fieldProps.value)
              ? (fieldProps.value as string[])
              : [];
            return (
              <EditorShell>
                <Select
                  {...portalMenuProps}
                  isMulti={multiple}
                  isClearable={false}
                  options={options}
                  value={
                    multiple
                      ? options.filter((option) => selected.includes(option.value))
                      : options.find((option) => option.value === selected[0]) ?? null
                  }
                  placeholder={placeholder}
                  autoFocus
                  defaultMenuIsOpen
                  isDisabled={saving}
                  testId={`${testId}-input`}
                  onChange={(choice) => {
                    if (multiple) {
                      const list = Array.isArray(choice) ? choice : [];
                      fieldProps.onChange(
                        (list as MemberOption[]).map((option) => option.value),
                      );
                    } else {
                      const option = choice as MemberOption | null;
                      fieldProps.onChange(option ? [option.value] : []);
                    }
                  }}
                />
                <EditorFooter
                  errorMessage={fieldProps.errorMessage}
                  saving={saving}
                  testId={testId}
                  onCancel={cancel}
                />
              </EditorShell>
            );
          }}
        />
      ) : (
        view
      )}
    </FieldShell>
  );
}

// --- choice fields (severity) ---

interface InlineChoiceFieldProps {
  testId: string;
  label?: ReactNode;
  canEdit: boolean;
  value: string;
  options: { label: string; value: string }[];
  editLabel: string;
  onSave: (value: string) => Promise<boolean>;
}

export function InlineChoiceField({
  testId,
  label,
  canEdit,
  value,
  options,
  editLabel,
  onSave,
}: InlineChoiceFieldProps) {
  const [editing, setEditing] = useState(false);
  const { saving, confirm, cancel } = useInlineSave(onSave, () => setEditing(false));
  const current = options.find((option) => option.value === value);

  const view = (
    <div className="rdm-inline-read">
      <Text size="small">{current?.label ?? value ?? "未设置"}</Text>
    </div>
  );

  return (
    <FieldShell label={label} testId={testId}>
      {canEdit ? (
        <InlineEdit<string>
          testId={testId}
          editButtonLabel={editLabel}
          isEditing={editing}
          defaultValue={value}
          keepEditViewOpenOnBlur
          hideActionButtons
          readViewFitContainerWidth
          onEdit={() => setEditing(true)}
          onCancel={cancel}
          onConfirm={confirm}
          readView={() => view}
          editView={(fieldProps) => (
            <EditorShell>
              <Select
                {...portalMenuProps}
                isClearable={false}
                options={options}
                value={
                  options.find(
                    (option) => option.value === String(fieldProps.value ?? ""),
                  ) ?? null
                }
                autoFocus
                defaultMenuIsOpen
                isDisabled={saving}
                testId={`${testId}-input`}
                onChange={(choice) => {
                  const option = choice as { value: string } | null;
                  if (option) fieldProps.onChange(option.value);
                }}
              />
              <EditorFooter
                errorMessage={fieldProps.errorMessage}
                saving={saving}
                testId={testId}
                onCancel={cancel}
              />
            </EditorShell>
          )}
        />
      ) : (
        view
      )}
    </FieldShell>
  );
}
