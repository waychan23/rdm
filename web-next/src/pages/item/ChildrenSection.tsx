import { useEffect, useMemo, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Inline, Stack } from "@atlaskit/primitives/compiled";

import FormField from "../../components/FormField";
import TextButton from "../../components/TextButton";
import WorkItemPicker, { type WorkItemOption } from "../../components/WorkItemPicker";
import { api, errorCause } from "../../lib/api";
import { useNotify } from "../../lib/flags";
import type { WorkItem } from "../../types";
import CreateWorkItemDialog from "../../workitems/CreateWorkItemDialog";

function toWorkItemOption(item: WorkItem): WorkItemOption {
  return {
    label: `${item.display_id} · ${item.title}`,
    value: item.display_id,
    id: item.id,
    display_id: item.display_id,
    title: item.title,
    kind: item.kind,
    status: item.status,
    row_version: item.row_version,
  };
}

interface LinkChildDialogProps {
  open: boolean;
  projectKey: string;
  parent: WorkItem;
  allowedKinds: string[];
  excludeIds: string[];
  onClose: () => void;
  onChanged: () => void;
}

function LinkChildDialog({
  open,
  projectKey,
  parent,
  allowedKinds,
  excludeIds,
  onClose,
  onChanged,
}: LinkChildDialogProps) {
  const notify = useNotify();
  const [existing, setExisting] = useState<WorkItemOption | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setExisting(null);
    setSaving(false);
  }, [open]);

  const submit = async () => {
    if (saving) return;
    if (!existing) {
      notify.error("请选择要关联的工作项");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/work-items/${existing.display_id}/reparent`, {
        parent: parent.display_id,
        row_version: existing.row_version,
      });
      notify.success(`已把 ${existing.display_id} 挂到 ${parent.display_id}`);
      onChanged();
      onClose();
    } catch (e) {
      notify.error("关联子项失败", errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="640px" testId="link-child-dialog">
          <ModalHeader>
            <ModalTitle>关联已有工作项到 {parent.display_id}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label="已有工作项">
                <WorkItemPicker
                  projectKey={projectKey}
                  allowedKinds={allowedKinds}
                  excludeIds={excludeIds}
                  value={existing}
                  onChange={setExisting}
                  placeholder="搜索并选择工作项"
                  testId="link-child-existing"
                />
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="link-child-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              isDisabled={!existing}
              onClick={() => void submit()}
              testId="link-child-submit"
            >
              关联
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
  const [showCreate, setShowCreate] = useState(false);
  const [showLink, setShowLink] = useState(false);
  const parentOption = useMemo(() => toWorkItemOption(parent), [parent]);
  const excludeIds = useMemo(
    () => [parent.id, ...children.map((child) => child.id)],
    [parent.id, children],
  );

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

  const disabled = allowedKinds.length === 0;

  return (
    <div data-testid="item-panel-children">
      <div className="rdm-item-section-head">
        <div className="rdm-item-section-label">子项（{children.length}）</div>
        <Inline space="space.100">
          <Button
            spacing="compact"
            testId="item-child-create"
            isDisabled={disabled}
            onClick={() => setShowCreate(true)}
          >
            新建子项
          </Button>
          <Button
            appearance="subtle"
            spacing="compact"
            testId="item-child-link"
            isDisabled={disabled}
            onClick={() => setShowLink(true)}
          >
            关联已有
          </Button>
        </Inline>
      </div>
      {children.length === 0 ? (
        <div className="rdm-item-empty" data-testid="item-children-empty">
          {disabled
            ? "该类型不能有子项"
            : "还没有子项；点击「新建子项」或「关联已有」。"}
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
      <CreateWorkItemDialog
        open={showCreate}
        projectKey={projectKey}
        initialParent={parentOption}
        allowedKinds={allowedKinds}
        parentLocked
        dialogTitle={`新建子项到 ${parent.display_id}`}
        onClose={() => setShowCreate(false)}
        onCreated={() => onChanged()}
      />
      <LinkChildDialog
        open={showLink}
        projectKey={projectKey}
        parent={parent}
        allowedKinds={allowedKinds}
        excludeIds={excludeIds}
        onClose={() => setShowLink(false)}
        onChanged={onChanged}
      />
    </div>
  );
}
