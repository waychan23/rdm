import { useEffect, useState } from "react";

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

interface Props {
  attachment: Attachment | null;
  onClose: () => void;
}

function previewKind(mime: string | null | undefined): "pdf" | "text" | "image" | "none" {
  const value = (mime ?? "").toLowerCase();
  if (value === "application/pdf") return "pdf";
  if (value.startsWith("text/") || value.includes("json") || value.includes("markdown")) {
    return "text";
  }
  if (value.startsWith("image/")) return "image";
  return "none";
}

export default function AttachmentPreviewDialog({ attachment, onClose }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const kind = previewKind(attachment?.mime);

  useEffect(() => {
    if (!attachment) return;
    let revoked: string | null = null;
    let alive = true;
    setUrl(null);
    setText(null);
    setError(null);
    if (kind === "text") {
      api
        .fetchBlob(attachment.download_url)
        .then((blob) => blob.text())
        .then((value) => alive && setText(value.slice(0, 200_000)))
        .catch(() => alive && setError("无法读取文本内容"));
    } else if (kind === "pdf" || kind === "image") {
      api
        .blobUrl(attachment.download_url)
        .then((value) => {
          if (!alive) {
            URL.revokeObjectURL(value);
            return;
          }
          revoked = value;
          setUrl(value);
        })
        .catch(() => alive && setError("无法加载附件"));
    }
    return () => {
      alive = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [attachment, kind]);

  return (
    <ModalTransition>
      {attachment && (
        <ModalDialog onClose={onClose} width="900px" testId="attachment-preview-dialog">
          <ModalHeader>
            <ModalTitle>{attachment.filename}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Box testId="attachment-preview-body" style={{ minHeight: 240 }}>
              {kind === "none" ? (
                <Button onClick={() => api.download(attachment.download_url, attachment.filename)}>
                  下载附件
                </Button>
              ) : error ? (
                <Box>{error}</Box>
              ) : kind === "text" ? (
                text === null ? (
                  <Spinner />
                ) : (
                  <pre style={{ whiteSpace: "pre-wrap", maxHeight: "60vh", overflow: "auto" }}>
                    {text}
                  </pre>
                )
              ) : url === null ? (
                <Spinner />
              ) : kind === "pdf" ? (
                <iframe
                  title={attachment.filename}
                  src={url}
                  style={{ width: "100%", height: "60vh", border: 0 }}
                />
              ) : (
                <img
                  src={url}
                  alt={attachment.filename}
                  style={{ maxWidth: "100%", maxHeight: "60vh" }}
                />
              )}
            </Box>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              关闭
            </Button>
            <Button onClick={() => api.download(attachment.download_url, attachment.filename)}>
              下载
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
