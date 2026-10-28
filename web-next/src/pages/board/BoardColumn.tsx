import { useEffect, useRef, useState, type ReactNode } from "react";

import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { token } from "@atlaskit/tokens";

import StatusLozenge from "../../workitems/status";

interface Props {
  status: string;
  count: number;
  children: ReactNode;
}

export default function BoardColumn({ status, count, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [isOver, setIsOver] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return dropTargetForElements({
      element: el,
      getData: () => ({ status }),
      onDragEnter: () => setIsOver(true),
      onDragLeave: () => setIsOver(false),
      onDrop: () => setIsOver(false),
    });
  }, [status]);

  return (
    <div
      ref={ref}
      style={{
        flex: "0 0 280px",
        background: isOver
          ? token("color.background.selected")
          : token("elevation.surface.sunken"),
        borderRadius: token("radius.small"),
        padding: token("space.100"),
        display: "flex",
        flexDirection: "column",
        outline: isOver ? `2px dashed ${token("color.border.focused")}` : "none",
        outlineOffset: "-2px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: 32,
          padding: `0 ${token("space.100")} ${token("space.100")}`,
        }}
      >
        <StatusLozenge status={status} />
        <span style={{ color: token("color.text.subtlest"), fontSize: 12 }}>{count}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: token("space.100"), minHeight: 80 }}>
        {children}
      </div>
    </div>
  );
}
