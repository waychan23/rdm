import { useMemo } from "react";

import { renderMarkdown } from "../lib/markdown";

export default function MarkdownText({ source }: { source: string | null | undefined }) {
  const html = useMemo(() => renderMarkdown(source), [source]);
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}
