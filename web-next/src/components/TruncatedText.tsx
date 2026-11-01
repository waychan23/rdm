import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import Tooltip from "@atlaskit/tooltip";

interface Props {
  /** Full text shown in the tooltip. */
  text: string;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  testId?: string;
}

/**
 * A single-line text node that truncates with ellipsis (the caller supplies
 * the truncation class) and shows the full text in an ADS tooltip only while
 * it actually overflows (RDM-62).
 */
export default function TruncatedText({
  text,
  children,
  className,
  style,
  testId,
}: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      // clientWidth is 0 for hidden elements; keep the last real state then.
      if (element.clientWidth > 0) {
        setOverflowing(element.scrollWidth > element.clientWidth + 1);
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text]);

  const node = (
    <span ref={ref} className={className} style={style} data-testid={testId}>
      {children ?? text}
    </span>
  );

  return overflowing ? <Tooltip content={text}>{node}</Tooltip> : node;
}
