// Render user-provided markdown, sanitized before dangerouslySetInnerHTML.
// Authenticated attachment images have their src stripped here; MarkdownText
// resolves them through lib/attachmentImages (Bearer -> object URL).
import { marked } from "marked";
import DOMPurify from "dompurify";

import { isAttachmentDownloadUrl } from "./attachmentImages";

export interface PreparedMarkdown {
  html: string;
  images: string[];
}

export function prepareMarkdown(source: string | null | undefined): PreparedMarkdown {
  if (!source) return { html: "", images: [] };
  const raw = marked.parse(source, { async: false, breaks: true }) as string;
  const clean = DOMPurify.sanitize(raw, {
    // No data: images — pasted base64 must never be rendered (files only).
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|\/|#)/i,
  });
  const doc = new DOMParser().parseFromString(clean, "text/html");
  const images: string[] = [];
  doc.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src") ?? "";
    if (isAttachmentDownloadUrl(src)) {
      img.setAttribute("data-attachment-src", src);
      img.removeAttribute("src");
      images.push(src);
    }
  });
  return { html: doc.body.innerHTML, images: [...new Set(images)] };
}

export function renderMarkdown(source: string | null | undefined): string {
  return prepareMarkdown(source).html;
}
