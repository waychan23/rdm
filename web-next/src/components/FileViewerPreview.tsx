// Lazy-loaded bridge to @open-file-viewer/core. Kept in its own module so the
// viewer runtime and its on-demand format chunks stay out of the initial bundle.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { FileViewer } from "@open-file-viewer/react";
import {
  archivePlugin,
  audioPlugin,
  emailPlugin,
  fallbackPlugin,
  imagePlugin,
  officePlugin,
  pdfPlugin,
  textPlugin,
  videoPlugin,
  type PreviewPlugin,
} from "@open-file-viewer/core";
import "@open-file-viewer/core/style.css";
import pdfWorkerSrc from "pdfjs-dist/build/pdf.worker.mjs?url";
import pdfLegacyWorkerSrc from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";

import Spinner from "@atlaskit/spinner";

import { fetchAttachmentBlob } from "../api/attachments-api";
import type { Attachment } from "../types";

interface Props {
  attachment: Attachment;
}

export default function FileViewerPreview({ attachment }: Props) {
  const { t, i18n } = useTranslation("components");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [failed, setFailed] = useState(false);
  const locale = i18n.language.startsWith("en") ? "en-US" : "zh-CN";
  const plugins = useMemo<PreviewPlugin[]>(
    () => [
      imagePlugin(),
      textPlugin(),
      pdfPlugin({ workerSrc: pdfWorkerSrc, legacyWorkerSrc: pdfLegacyWorkerSrc }),
      officePlugin(),
      archivePlugin(),
      emailPlugin(),
      audioPlugin(),
      videoPlugin(),
      fallbackPlugin(),
    ],
    [],
  );

  useEffect(() => {
    let alive = true;
    setBlob(null);
    setFailed(false);
    fetchAttachmentBlob(attachment.download_url)
      .then((value) => alive && setBlob(value))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [attachment.id, attachment.download_url]);

  if (failed) return <span>{t("attachment.loadFailed")}</span>;
  if (!blob) return <Spinner />;

  return (
    <FileViewer
      file={blob}
      fileName={attachment.filename}
      mimeType={attachment.mime ?? undefined}
      width="100%"
      height="60vh"
      fit="contain"
      toolbar
      theme="light"
      locale={locale}
      plugins={plugins}
      fallback="download"
    />
  );
}
