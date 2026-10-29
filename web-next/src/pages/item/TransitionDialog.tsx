import { useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import TextArea from "@atlaskit/textarea";

interface Props {
  to: string | null;
  onCancel: () => void;
  onConfirm: (reason: string | null) => Promise<void> | void;
}

// Reason prompt for a workflow transition; the reason is optional.
export default function TransitionDialog({ to, onCancel, onConfirm }: Props) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  return (
    <ModalTransition>
      {to && (
        <ModalDialog
          onClose={onCancel}
          testId="transition-dialog"
          onCloseComplete={(_e) => {
            setReason("");
            setSaving(false);
          }}
        >
          <ModalHeader>
            <ModalTitle>状态流转 → {to}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <TextArea
              autoFocus
              value={reason}
              minimumRows={3}
              placeholder="流转原因（可留空）"
              testId="transition-reason"
              onChange={(e) => setReason(e.currentTarget.value)}
            />
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onCancel} testId="transition-cancel">
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              testId="transition-confirm"
              onClick={async () => {
                setSaving(true);
                try {
                  await onConfirm(reason.trim() || null);
                } finally {
                  setSaving(false);
                }
              }}
            >
              流转
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
