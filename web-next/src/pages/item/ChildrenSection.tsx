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
import { useTranslation } from "react-i18next";

import FormField from "../../components/FormField";
import PersonCell from "../../components/PersonCell";
import WorkItemPicker, {
  toWorkItemOption,
  type WorkItemOption,
} from "../../components/WorkItemPicker";
import { api, errorCause } from "../../lib/api";
import { useNotify } from "../../lib/flags";
import type { WorkItem } from "../../types";
import CreateWorkItemDialog from "../../workitems/CreateWorkItemDialog";
import StatusLozenge from "../../workitems/status";

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
  const { t } = useTranslation("item");
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
      notify.error(t("children.selectRequired"));
      return;
    }
    setSaving(true);
    try {
      await api.post(`/work-items/${existing.display_id}/reparent`, {
        parent: parent.display_id,
        row_version: existing.row_version,
      });
      notify.success(
        t("children.linked", {
          child: existing.display_id,
          parent: parent.display_id,
        }),
      );
      onChanged();
      onClose();
    } catch (e) {
      notify.error(t("children.linkFailed"), errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="640px" testId="link-child-dialog">
          <ModalHeader>
            <ModalTitle>{t("children.linkTitle", { id: parent.display_id })}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label={t("children.existing")}>
                <WorkItemPicker
                  projectKey={projectKey}
                  allowedKinds={allowedKinds}
                  excludeIds={excludeIds}
                  value={existing}
                  onChange={setExisting}
                  placeholder={t("children.searchPlaceholder")}
                  testId="link-child-existing"
                />
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="link-child-cancel">
              {t("children.cancel")}
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              isDisabled={!existing}
              onClick={() => void submit()}
              testId="link-child-submit"
            >
              {t("children.link")}
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
  const { t } = useTranslation("item");
  const [showCreate, setShowCreate] = useState(false);
  const [showLink, setShowLink] = useState(false);
  const parentOption = useMemo(() => toWorkItemOption(parent), [parent]);
  const excludeIds = useMemo(
    () => [parent.id, ...children.map((child) => child.id)],
    [parent.id, children],
  );

  const disabled = allowedKinds.length === 0;

  return (
    <div data-testid="item-panel-children">
      <div className="rdm-item-section-head">
        <div className="rdm-item-section-label">
          {t("children.sectionLabel", { total: children.length })}
        </div>
        <Inline space="space.100">
          <Button
            spacing="compact"
            testId="item-child-create"
            isDisabled={disabled}
            onClick={() => setShowCreate(true)}
          >
            {t("children.create")}
          </Button>
          <Button
            appearance="subtle"
            spacing="compact"
            testId="item-child-link"
            isDisabled={disabled}
            onClick={() => setShowLink(true)}
          >
            {t("children.linkExisting")}
          </Button>
        </Inline>
      </div>
      {children.length === 0 ? (
        <div className="rdm-item-empty" data-testid="item-children-empty">
          {disabled ? t("children.emptyDisabled") : t("children.empty")}
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
              <span className="rdm-item-child-status">
                <StatusLozenge status={child.status} />
              </span>
              <span className="rdm-item-child-assignee">
                <PersonCell name={child.assignee?.name} />
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
        dialogTitle={t("children.createTitle", { id: parent.display_id })}
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
