import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
import Textfield from "@atlaskit/textfield";

import FormField from "../../components/FormField";
import MarkdownEditor from "../../components/MarkdownEditor";

export interface ReleaseFormValues {
  name: string;
  description_md: string;
  target_date: string | null;
}

interface Props {
  open: boolean;
  title: string;
  projectKey: string;
  initial?: Partial<ReleaseFormValues>;
  onClose: () => void;
  onSave: (values: ReleaseFormValues) => Promise<void> | void;
}

export default function ReleaseFormDialog({
  open,
  title,
  projectKey,
  initial,
  onClose,
  onSave,
}: Props) {
  const { t } = useTranslation("releases");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description_md ?? "");
  const [target, setTarget] = useState(initial?.target_date ?? "");
  const [saving, setSaving] = useState(false);

  // Re-seed the form on every open so edit reflects the selected release.
  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setDescription(initial?.description_md ?? "");
    setTarget(initial?.target_date ?? "");
    setSaving(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        description_md: description,
        target_date: target || null,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog
          onClose={onClose}
          width="480px"
          // Backdrop clicks must not discard a half-filled form (RDM-163).
          shouldCloseOnOverlayClick={false}
          testId="release-form-dialog"
        >
          <ModalHeader>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label={t("form.name")} htmlFor="release-name">
                <Textfield
                  id="release-name"
                  value={name}
                  autoFocus
                  placeholder="v1.0.0"
                  testId="release-form-name"
                  onChange={(e) => setName(e.currentTarget.value)}
                />
              </FormField>
              <FormField label={t("form.description")}>
                <MarkdownEditor
                  value={description}
                  onChange={setDescription}
                  projectKey={projectKey}
                  minimumRows={4}
                  testId="release-form-description"
                  onSubmit={() => void submit()}
                />
              </FormField>
              <FormField label={t("form.targetDate")}>
                <DatePicker
                  placeholder={t("form.targetPlaceholder")}
                  value={target || ""}
                  testId="release-form-target-date"
                  onChange={(value) => setTarget(value)}
                />
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="release-form-cancel">
              {t("form.cancel")}
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={() => void submit()}
              testId="release-form-submit"
            >
              {t("form.save")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
