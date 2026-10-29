import { useEffect, useRef, useState } from "react";

import { draggable } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives";
import { token } from "@atlaskit/tokens";

import PersonCell from "../../components/PersonCell";
import PriorityMark from "../../components/PriorityMark";
import TypeKindIcon from "../../components/TypeKindIcon";
import type { WorkItem } from "../../types";

interface Props {
  item: WorkItem;
  onOpen: (item: WorkItem) => void;
}

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
    <div
      ref={ref}
      role="button"
      tabIndex={0}
      data-testid={`board-card-${item.display_id}`}
      onClick={() => onOpen(item)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(item);
        }
      }}
      style={{
        background: token("elevation.surface"),
        border: `1px solid ${token("color.border")}`,
        borderRadius: token("radius.small"),
        padding: token("space.150"),
        cursor: "grab",
        opacity: dragging ? 0.4 : 1,
      }}
    >
      <Stack space="space.100">
        <Inline space="space.100" alignBlock="center">
          <TypeKindIcon kind={item.kind} />
          <Box
            as="span"
            style={{
              color: token("color.link"),
              font: token("font.body.small"),
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {item.display_id}
          </Box>
          <Box as="span" style={{ marginLeft: "auto" }}>
            <PriorityMark priority={item.priority} />
          </Box>
        </Inline>
        <Text size="small" color="color.text">
          {item.title}
        </Text>
        <PersonCell name={item.assignee?.name} />
      </Stack>
    </div>
  );
}
