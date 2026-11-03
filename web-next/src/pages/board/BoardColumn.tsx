import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import Spinner from "@atlaskit/spinner";
import { Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";

import StatusLozenge from "../../workitems/status";
import { readColumnPosition, rememberColumnPosition } from "../../lib/scrollMemory";

interface Props {
  status: string;
  /** Per-project/request key for restoring the column's scroll offset. */
  scrollKey: string;
  /** Unpaginated count for the column header. */
  count: number;
  /** More pages can be fetched when the column scrolls to the bottom. */
  hasMore?: boolean;
  loadingMore?: boolean;
  loadFailed?: boolean;
  onLoadMore?: () => void;
  children: ReactNode;
}

export default function BoardColumn({
  status,
  scrollKey,
  count,
  hasMore = false,
  loadingMore = false,
  loadFailed = false,
  onLoadMore,
  children,
}: Props) {
  const { t } = useTranslation("projects");
  const ref = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [isOver, setIsOver] = useState(false);

  // Board remounts on a menu switch; restore the column body offset once the
  // cached cards are on screen (RDM-80).
  useLayoutEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const top = readColumnPosition(scrollKey);
    if (top !== null) body.scrollTop = top;
  }, [scrollKey]);

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

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const el = event.currentTarget;
    rememberColumnPosition(scrollKey, el.scrollTop);
    if (!hasMore || loadingMore || !onLoadMore) return;
    // Fetch the next page just before the bottom is reached.
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) onLoadMore();
  };

  return (
    <div
      ref={ref}
      data-testid={`board-column-${status}`}
      style={{
        flex: "0 0 280px",
        height: "100%",
        minHeight: 0,
        background: isOver
          ? token("color.background.selected")
          : token("elevation.surface.sunken"),
        borderRadius: token("radius.small"),
        padding: token("space.100"),
        display: "flex",
        flexDirection: "column",
        gap: token("space.100"),
        outline: isOver ? `2px dashed ${token("color.border.focused")}` : "none",
        outlineOffset: "-2px",
      }}
    >
      {/* Outside the scroll body: column headers stay put while cards scroll. */}
      <Inline spread="space-between" alignBlock="center" space="space.100">
        <StatusLozenge status={status} />
        <Text size="small" color="color.text.subtlest" testId={`board-column-count-${status}`}>
          {count}
        </Text>
      </Inline>
      <div
        ref={bodyRef}
        data-testid={`board-column-body-${status}`}
        onScroll={handleScroll}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          // Do not contain wheel/trackpad scrolling: horizontal swipes over a
          // column must chain to the board's horizontal scroller (RDM-73).
          overflowX: "hidden",
          paddingBlockEnd: token("space.150"),
        }}
      >
        <Stack space="space.100">{children}</Stack>
        {loadingMore && (
          <Inline alignBlock="center" space="space.050" xcss={styles.centered}>
            <Spinner size="small" />
            <Text size="small" color="color.text.subtlest">
              {t("board.loadingMore")}
            </Text>
          </Inline>
        )}
        {loadFailed && (
          <Inline alignBlock="center" space="space.050" xcss={styles.message}>
            <Text size="small" color="color.text.danger">
              {t("board.columnLoadFailed")}
            </Text>
          </Inline>
        )}
        {!hasMore && !loadingMore && count > 0 && (
          <Inline alignBlock="center" space="space.050" xcss={styles.message}>
            <Text size="small" color="color.text.subtlest" testId={`board-column-end-${status}`}>
              {t("board.noMore")}
            </Text>
          </Inline>
        )}
      </div>
    </div>
  );
}

const styles = cssMap({
  centered: {
    justifyContent: "center",
    paddingBlock: "var(--ds-space-100)",
  },
  // Column status/end messages share the card stack's width, so centering
  // needs an explicit flex row (Text is inline-level).
  message: {
    justifyContent: "center",
    paddingBlock: "var(--ds-space-100)",
  },
});
