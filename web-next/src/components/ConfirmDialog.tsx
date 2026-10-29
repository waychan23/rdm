import type { ReactNode } from "react";

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
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
  testId = "confirm-dialog",
}: Props) {
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
              {cancelLabel}
            </Button>
            <Button
              appearance={danger ? "danger" : "primary"}
              onClick={onConfirm}
              isLoading={busy}
              testId={`${testId}-confirm`}
            >
              {confirmLabel}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
