import { useEffect, useRef, useState } from "react";

import { draggable } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { token } from "@atlaskit/tokens";
import type { CSSProperties } from "react";

import PersonCell from "../../components/PersonCell";
import PriorityMark from "../../components/PriorityMark";
import TypeKindIcon from "../../components/TypeKindIcon";
import type { WorkItem } from "../../types";

interface Props {
  item: WorkItem;
  onOpen: (item: WorkItem) => void;
}

const cardStyle = (dragging: boolean): CSSProperties => ({
  background: token("elevation.surface"),
  border: `1px solid ${token("color.border")}`,
  borderRadius: token("radius.small"),
  padding: token("space.150"),
  cursor: "grab",
  opacity: dragging ? 0.4 : 1,
});

export default function BoardCard({ item, onOpen }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return draggable({
      element: el,
      getInitialData: () => ({ itemId: item.id, status: item.status }),
      onDragStart: () => setDragging(true),
      onDrop: () => setDragging(false),
    });
  }, [item.id, item.status]);

  return (
    <div ref={ref} style={cardStyle(dragging)} onClick={() => onOpen(item)}>
      <div style={{ display: "flex", alignItems: "center", gap: token("space.100") }}>
        <TypeKindIcon kind={item.kind} />
        <span
          style={{
            color: token("color.link"),
            fontSize: 12,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {item.display_id}
        </span>
        <span style={{ marginLeft: "auto" }}>
          <PriorityMark priority={item.priority} />
        </span>
      </div>
      <div style={{ margin: `${token("space.100")} 0` }}>{item.title}</div>
      <div style={{ color: token("color.text.subtlest") }}>
        <PersonCell name={item.assignee?.name} />
      </div>
    </div>
  );
}
