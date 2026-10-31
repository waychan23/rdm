import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";

interface Props {
  open: boolean;
  title: ReactNode;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  testId?: string;
}

/** Confirmation dialog using the ADS modal instead of window.confirm. */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel,
  danger = false,
  busy = false,
  onConfirm,
  onClose,
  testId = "confirm-dialog",
}: Props) {
  const { t } = useTranslation("common");
  const confirmText = confirmLabel ?? t("actions.confirm");
  const cancelText = cancelLabel ?? t("actions.cancel");
  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} testId={testId} width="420px">
          <ModalHeader>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
          <ModalBody>{children}</ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId={`${testId}-cancel`}>
              {cancelText}
            </Button>
            <Button
              appearance={danger ? "danger" : "primary"}
              onClick={onConfirm}
              isLoading={busy}
              testId={`${testId}-confirm`}
            >
              {confirmText}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
