import { useEffect, useRef, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import MarkdownEditor, { type MarkdownImageClick } from "../../components/MarkdownEditor";
import { uploadProjectAttachment } from "../../api/attachments-api";
import { errorCause } from "../../lib/api";
import { useNotify } from "../../lib/flags";
import type { Attachment } from "../../types";

interface Props {
  open: boolean;
  projectKey: string;
  itemId: string;
  stepName: string;
  noteRequired: boolean;
  onClose: () => void;
  onConfirm: (noteMd: string, attachmentIds: string[]) => Promise<void>;
  onImageClick?: (image: MarkdownImageClick) => void;
}

export default function StepExecuteDialog({
  open,
  projectKey,
  itemId,
  stepName,
  noteRequired,
  onClose,
  onConfirm,
  onImageClick,
}: Props) {
  const { t } = useTranslation("item");
  const notify = useNotify();
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<{ name: string; id: string }[]>([]);
  const pendingIds = useRef<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadingDraft, setUploadingDraft] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setNote("");
    setPending([]);
    pendingIds.current = [];
    setSaving(false);
    setUploading(false);
  }, [open]);

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        form.append("owner_type", "work_item");
        form.append("owner_ref", itemId);
        const attachment = await uploadProjectAttachment(projectKey, form);
        pendingIds.current.push(attachment.id);
        setPending((current) => [...current, { name: file.name, id: attachment.id }]);
      }
      notify.success(t("stepExecute.uploaded"));
    } catch (e) {
      notify.error(t("stepExecute.uploadFailed"), errorCause(e)?.message);
    } finally {
      setUploading(false);
    }
  };

  const disabled =
    saving || uploading || uploadingDraft || (noteRequired && !note.trim());

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="640px" testId="step-execute-dialog">
          <ModalHeader>
            <ModalTitle>{t("stepExecute.title", { name: stepName })}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Text size="small" color="color.text.subtlest">
                {noteRequired ? t("stepExecute.noteRequired") : t("stepExecute.noteOptional")}{" "}
                {t("stepExecute.hint")}
              </Text>
              <MarkdownEditor
                value={note}
                onChange={setNote}
                projectKey={projectKey}
                minimumRows={4}
                autoFocus
                testId="step-execute-note"
                onImageClick={onImageClick}
                onUploadingChange={setUploadingDraft}
              />
              <input
                ref={fileInput}
                type="file"
                multiple
                hidden
                onChange={(e) => void upload(e.target.files)}
              />
              <Inline space="space.100" alignBlock="center" shouldWrap>
                <Button
                  spacing="compact"
                  isLoading={uploading}
                  testId="step-execute-attach"
                  onClick={() => fileInput.current?.click()}
                >
                  {t("stepExecute.attach")}
                </Button>
                {pending.map((file) => (
                  <Text key={file.id} size="small" color="color.text.subtlest">
                    📎 {file.name}
                  </Text>
                ))}
              </Inline>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="step-execute-cancel">
              {t("stepExecute.cancel")}
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              isDisabled={disabled}
              testId="step-execute-confirm"
              onClick={async () => {
                setSaving(true);
                try {
                  await onConfirm(
                    note.trim() ||
                    (pendingIds.current.length ? t("stepExecute.defaultNote") : ""),
                    pendingIds.current,
                  );
                } finally {
                  setSaving(false);
                }
              }}
            >
              {t("stepExecute.submit")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
