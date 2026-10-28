// Render user-provided markdown, sanitized before dangerouslySetInnerHTML.
import { marked } from "marked";
import DOMPurify from "dompurify";

export function renderMarkdown(source: string | null | undefined): string {
  if (!source) return "";
  const raw = marked.parse(source, { async: false, breaks: true }) as string;
  return DOMPurify.sanitize(raw);
}
