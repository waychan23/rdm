import { useEffect, useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Stack, Text } from "@atlaskit/primitives/compiled";
import TextArea from "@atlaskit/textarea";

interface Props {
  open: boolean;
  stepName: string;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}

export default function StepRejectDialog({ open, stepName, onClose, onConfirm }: Props) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setReason("");
      setSaving(false);
    }
  }, [open]);

  const submit = async () => {
    if (!reason.trim()) return;
    setSaving(true);
    try {
      await onConfirm(reason.trim());
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="520px" testId="step-reject-dialog">
          <ModalHeader>
            <ModalTitle>拒绝步骤 · {stepName}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Text size="small" color="color.text.subtlest">
                拒绝后本步骤终止，工作项保持当前状态；已完成的其他执行记录保留。
              </Text>
              <TextArea
                value={reason}
                onChange={(e) => setReason(e.currentTarget.value)}
                minimumRows={4}
                testId="step-reject-reason"
                placeholder="请填写拒绝理由"
                autoFocus
              />
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              取消
            </Button>
            <Button
              appearance="danger"
              isDisabled={!reason.trim()}
              isLoading={saving}
              testId="step-reject-confirm"
              onClick={() => void submit()}
            >
              拒绝
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
