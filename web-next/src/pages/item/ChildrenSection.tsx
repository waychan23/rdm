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
import { RadioGroup } from "@atlaskit/radio";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";

import FormField from "../../components/FormField";
import MarkdownEditor from "../../components/MarkdownEditor";
import TextButton from "../../components/TextButton";
import WorkItemPicker, { type WorkItemOption } from "../../components/WorkItemPicker";
import { api, errorCause } from "../../lib/api";
import { useNotify } from "../../lib/flags";
import { portalMenuProps } from "../../lib/portalMenu";
import type { WorkItem } from "../../types";

interface AddChildDialogProps {
  open: boolean;
  projectKey: string;
  parent: WorkItem;
  allowedKinds: string[];
  excludeIds: string[];
  onClose: () => void;
  onChanged: () => void;
}

export function AddChildDialog({
  open,
  projectKey,
  parent,
  allowedKinds,
  excludeIds,
  onClose,
  onChanged,
}: AddChildDialogProps) {
  const notify = useNotify();
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [kind, setKind] = useState(allowedKinds[0] ?? "task");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [existing, setExisting] = useState<WorkItemOption | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMode("new");
    setKind(allowedKinds[0] ?? "task");
    setTitle("");
    setDescription("");
    setExisting(null);
    setSaving(false);
  }, [open, allowedKinds]);

  const submit = async () => {
    if (saving) return;
    setSaving(true);
    try {
      if (mode === "new") {
        if (!title.trim()) {
          notify.error("请填写标题");
          return;
        }
        await api.post(`/projects/${projectKey}/work-items`, {
          kind,
          title: title.trim(),
          description_md: description || null,
          parent: parent.display_id,
        });
      } else {
        if (!existing) {
          notify.error("请选择要关联的工作项");
          return;
        }
        await api.post(`/work-items/${existing.display_id}/reparent`, {
          parent: parent.display_id,
          row_version: existing.row_version,
        });
      }
      onChanged();
      onClose();
    } catch (e) {
      notify.error("添加子项失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="640px" testId="add-child-dialog">
          <ModalHeader>
            <ModalTitle>添加子项到 {parent.display_id}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <RadioGroup
                options={[
                  { name: "child-mode", value: "new", label: "新建子项" },
                  { name: "child-mode", value: "existing", label: "关联已有工作项" },
                ]}
                value={mode}
                onChange={(e) => setMode(e.currentTarget.value as "new" | "existing")}
              />
              {mode === "new" ? (
                <>
                  <FormField label="类型" htmlFor="child-kind">
                    <Select
                      {...portalMenuProps}
                      inputId="child-kind"
                      options={allowedKinds.map((value) => ({ label: value, value }))}
                      value={{ label: kind, value: kind }}
                      onChange={(opt) =>
                        setKind((opt as { value: string } | null)?.value ?? kind)
                      }
                      testId="add-child-kind"
                    />
                  </FormField>
                  <FormField label="标题" htmlFor="child-title">
                    <Textfield
                      id="child-title"
                      value={title}
                      testId="add-child-title"
                      onChange={(e) => setTitle(e.currentTarget.value)}
                    />
                  </FormField>
                  <FormField label="描述（Markdown）">
                    <MarkdownEditor
                      value={description}
                      onChange={setDescription}
                      projectKey={projectKey}
                      minimumRows={3}
                      testId="add-child-description"
                    />
                  </FormField>
                </>
              ) : (
                <FormField label="已有工作项">
                  <WorkItemPicker
                    projectKey={projectKey}
                    allowedKinds={allowedKinds}
                    excludeIds={excludeIds}
                    value={existing}
                    onChange={setExisting}
                    placeholder="搜索并选择工作项"
                    testId="add-child-existing"
                  />
                </FormField>
              )}
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="add-child-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={() => void submit()}
              testId="add-child-submit"
            >
              添加
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}

interface ChildrenSectionProps {
  projectKey: string;
  parent: WorkItem;
  children: WorkItem[];
  allowedKinds: string[];
  onOpen: (id: string) => void;
  onChanged: () => void;
}

export default function ChildrenSection({
  projectKey,
  parent,
  children,
  allowedKinds,
  onOpen,
  onChanged,
}: ChildrenSectionProps) {
  const notify = useNotify();
  const [showAdd, setShowAdd] = useState(false);

  const removeChild = async (child: WorkItem) => {
    try {
      await api.post(`/work-items/${child.display_id}/reparent`, {
        parent: null,
        row_version: child.row_version,
      });
      notify.success(`已解除 ${child.display_id} 的父子关系`);
      onChanged();
    } catch (e) {
      notify.error("解除失败", errorCause(e)?.message);
    }
  };

  return (
    <div data-testid="item-panel-children">
      <div className="rdm-item-section-head">
        <div className="rdm-item-section-label">子项（{children.length}）</div>
        <Button
          spacing="compact"
          testId="item-child-add"
          isDisabled={allowedKinds.length === 0}
          onClick={() => setShowAdd(true)}
        >
          添加子项
        </Button>
      </div>
      {children.length === 0 ? (
        <div className="rdm-item-empty" data-testid="item-children-empty">
          {allowedKinds.length === 0
            ? "该类型不能有子项"
            : "还没有子项；点击「添加子项」新建或关联已有工作项。"}
        </div>
      ) : (
        children.map((child) => (
          <div key={child.id} className="rdm-item-child">
            <span
              className="rdm-item-child-main"
              role="button"
              tabIndex={0}
              onClick={() => onOpen(child.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen(child.id);
                }
              }}
            >
              <span className="rdm-item-child-id">{child.display_id}</span>
              <span className="rdm-item-child-title">{child.title}</span>
              <span className="rdm-item-child-actions">
                <TextButton
                  danger
                  data-testid={`item-child-detach-${child.display_id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    void removeChild(child);
                  }}
                >
                  解除
                </TextButton>
              </span>
            </span>
          </div>
        ))
      )}
      <AddChildDialog
        open={showAdd}
        projectKey={projectKey}
        parent={parent}
        allowedKinds={allowedKinds}
        excludeIds={[parent.id, ...children.map((c) => c.id)]}
        onClose={() => setShowAdd(false)}
        onChanged={onChanged}
      />
    </div>
  );
}
