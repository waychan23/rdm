import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { prepareMarkdown } from "../lib/markdown";
import { acquireAttachmentImage, releaseAttachmentImage } from "../lib/attachmentImages";

export interface MarkdownImageClick {
  src: string;
  alt: string;
  original: string;
}

interface Props {
  source: string | null | undefined;
  className?: string;
  onImageClick?: (image: MarkdownImageClick) => void;
}

export default function MarkdownText({ source, className, onImageClick }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const prepared = useMemo(() => prepareMarkdown(source), [source]);
  const [resolved, setResolved] = useState<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    const acquired: string[] = [];
    const load = async () => {
      const pairs = await Promise.all(
        prepared.images.map(async (src) => {
          try {
            const url = await acquireAttachmentImage(src);
            acquired.push(src);
            return [src, url] as const;
          } catch {
            return null;
          }
        }),
      );
      if (!alive) return;
      const map: Record<string, string> = {};
      for (const pair of pairs) if (pair) map[pair[0]] = pair[1];
      setResolved(map);
    };
    void load();
    return () => {
      alive = false;
      for (const src of acquired) releaseAttachmentImage(src);
    };
  }, [prepared]);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    root.querySelectorAll<HTMLImageElement>("img[data-attachment-src]").forEach((img) => {
      const src = img.dataset.attachmentSrc;
      if (src && resolved[src] && img.src !== resolved[src]) {
        img.src = resolved[src];
      }
    });
  }, [resolved, prepared.html]);

  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!onImageClick) return;
    const img = (event.target as HTMLElement).closest("img");
    if (!img) return;
    const original = img.getAttribute("data-attachment-src") ?? img.getAttribute("src") ?? "";
    onImageClick({ src: img.getAttribute("src") ?? original, alt: img.alt, original });
  };

  const classes = className ? `md ${className}` : "md";
  return (
    <div
      ref={ref}
      className={classes}
      onClickCapture={handleClick}
      dangerouslySetInnerHTML={{ __html: prepared.html }}
    />
  );
}
