import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Spinner from "@atlaskit/spinner";
import { Box } from "@atlaskit/primitives/compiled";

import { api } from "../lib/api";
import type { Attachment } from "../types";

// The viewer runtime is loaded on first use; see FileViewerPreview.
const FileViewerPreview = lazy(() => import("./FileViewerPreview"));

interface Props {
  attachment: Attachment | null;
  onClose: () => void;
}

export default function AttachmentPreviewDialog({ attachment, onClose }: Props) {
  const { t } = useTranslation("components");

  return (
    <ModalTransition>
      {attachment && (
        <ModalDialog onClose={onClose} width="900px" testId="attachment-preview-dialog">
          <ModalHeader>
            <ModalTitle>{attachment.filename}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Box testId="attachment-preview-body" style={{ minHeight: 240 }}>
              <Suspense fallback={<Spinner />}>
                <FileViewerPreview attachment={attachment} />
              </Suspense>
            </Box>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              {t("attachment.close")}
            </Button>
            <Button onClick={() => api.download(attachment.download_url, attachment.filename)}>
              {t("attachment.download")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
