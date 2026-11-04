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
import { useTranslation } from "react-i18next";

interface Props {
  open: boolean;
  stepName: string;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}

export default function StepRejectDialog({ open, stepName, onClose, onConfirm }: Props) {
  const { t } = useTranslation("item");
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
        <ModalDialog
          onClose={onClose}
          width="520px"
          // Backdrop clicks must not discard a half-filled form (RDM-163).
          shouldCloseOnOverlayClick={false}
          testId="step-reject-dialog"
        >
          <ModalHeader>
            <ModalTitle>{t("stepReject.title", { name: stepName })}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Text size="small" color="color.text.subtlest">
                {t("stepReject.description")}
              </Text>
              <TextArea
                value={reason}
                onChange={(e) => setReason(e.currentTarget.value)}
                minimumRows={4}
                testId="step-reject-reason"
                placeholder={t("stepReject.reasonPlaceholder")}
                autoFocus
              />
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              {t("stepReject.cancel")}
            </Button>
            <Button
              appearance="danger"
              isDisabled={!reason.trim()}
              isLoading={saving}
              testId="step-reject-confirm"
              onClick={() => void submit()}
            >
              {t("stepReject.reject")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
