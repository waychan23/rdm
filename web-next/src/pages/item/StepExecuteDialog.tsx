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

import MarkdownEditor, { type MarkdownImageClick } from "../../components/MarkdownEditor";
import { api, errorCause } from "../../lib/api";
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
        const res = await api.upload<Attachment>(`/projects/${projectKey}/attachments`, form);
        pendingIds.current.push(res.data.id);
        setPending((current) => [...current, { name: file.name, id: res.data.id }]);
      }
      notify.success("附件已上传");
    } catch (e) {
      notify.error("上传失败", errorCause(e)?.message);
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
            <ModalTitle>执行步骤 · {stepName}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Text size="small" color="color.text.subtlest">
                {noteRequired ? "该步骤必须填写备注。" : "备注可留空。"} 备注支持 Markdown，
                可上传附件或粘贴图片。
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
                  添加附件
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
              取消
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
                    note.trim() || (pendingIds.current.length ? "（步骤备注）" : ""),
                    pendingIds.current,
                  );
                } finally {
                  setSaving(false);
                }
              }}
            >
              提交
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
