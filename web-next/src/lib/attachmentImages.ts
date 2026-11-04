// Authenticated attachment images are fetched with the Bearer token and
// exposed as revocable object URLs. MarkdownText uses this module so the same
// image is downloaded once even when it appears in the preview and the list.

import { attachmentBlobUrl } from "../api/attachments-api";

interface Entry {
  url?: string;
  promise?: Promise<string>;
  refs: number;
}

const cache = new Map<string, Entry>();

const ATTACHMENT_URL_RE = /\/api\/v1\/attachments\/([A-Za-z0-9]{10,32})\/(?:download|content)/;

export function attachmentIdFromUrl(src: string): string | null {
  return ATTACHMENT_URL_RE.exec(src)?.[1] ?? null;
}

export function isAttachmentDownloadUrl(src: string): boolean {
  return attachmentIdFromUrl(src) !== null;
}

export async function acquireAttachmentImage(src: string): Promise<string> {
  let entry = cache.get(src);
  if (!entry) {
    entry = { refs: 0 };
    cache.set(src, entry);
  }
  entry.refs += 1;
  if (entry.url) return entry.url;
  if (!entry.promise) {
    const current = entry;
    current.promise = attachmentBlobUrl(src)
      .then((url) => {
        if (cache.get(src) === current) {
          current.url = url;
        } else {
          // Released while the download was in flight.
          URL.revokeObjectURL(url);
        }
        return url;
      })
      .catch((error) => {
        if (cache.get(src) === current) cache.delete(src);
        throw error;
      });
  }
  return entry.promise as Promise<string>;
}

export function releaseAttachmentImage(src: string): void {
  const entry = cache.get(src);
  if (!entry) return;
  entry.refs -= 1;
  if (entry.refs > 0) return;
  if (entry.url) URL.revokeObjectURL(entry.url);
  cache.delete(src);
}
