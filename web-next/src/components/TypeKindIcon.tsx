import { token } from "@atlaskit/tokens";
import type { CSSProperties } from "react";

const LABELS: Record<string, string> = {
  epic: "E",
  story: "需",
  issue: "缺",
  task: "任",
};

// Bold accent backgrounds (color.background.accent.*.subtle) carry white text;
// 16px rounded letter chip, one accent per work-item kind.
const COLORS: Record<string, string> = {
  epic: token("color.background.accent.gray.subtle"),
  story: token("color.background.accent.green.subtle"),
  issue: token("color.background.accent.red.subtle"),
  task: token("color.background.accent.blue.subtle"),
};

const chipStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: token("space.200"),
  height: token("space.200"),
  borderRadius: token("radius.small"),
  font: token("font.body.small"),
  fontWeight: token("font.weight.medium"),
  color: token("color.text.inverse"),
  flexShrink: 0,
};

export default function TypeKindIcon({ kind }: { kind: string }) {
  return (
    <span
      style={{ ...chipStyle, backgroundColor: COLORS[kind] ?? token("color.background.accent.gray.subtle") }}
      aria-label={`类型 ${kind}`}
      role="img"
    >
      {LABELS[kind] ?? kind}
    </span>
  );
}
