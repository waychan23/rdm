import { token } from "@atlaskit/tokens";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import { kindLabel, kindShortLabel } from "../lib/labels";

// Subtle accent fill + the matching *bolder* accent text keeps AA contrast
// (white text on subtle backgrounds does not pass).
const COLORS: Record<string, { background: string; foreground: string }> = {
  epic: {
    background: token("color.background.accent.gray.subtle"),
    foreground: token("color.text.accent.gray.bolder"),
  },
  story: {
    background: token("color.background.accent.green.subtle"),
    foreground: token("color.text.accent.green.bolder"),
  },
  issue: {
    background: token("color.background.accent.red.subtle"),
    foreground: token("color.text.accent.red.bolder"),
  },
  task: {
    background: token("color.background.accent.blue.subtle"),
    foreground: token("color.text.accent.blue.bolder"),
  },
};

const FALLBACK = COLORS.epic;

const chipStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: token("space.200"),
  height: token("space.200"),
  borderRadius: token("radius.small"),
  font: token("font.body.small"),
  fontWeight: token("font.weight.medium"),
  flexShrink: 0,
};

export default function TypeKindIcon({ kind }: { kind: string }) {
  const { t } = useTranslation("common");
  const colors = COLORS[kind] ?? FALLBACK;
  return (
    <span
      style={{
        ...chipStyle,
        backgroundColor: colors.background,
        color: colors.foreground,
      }}
      aria-label={t("typeKindLabel", { kind: kindLabel(kind), defaultValue: kindLabel(kind) })}
      role="img"
      data-testid={`type-icon-${kind}`}
    >
      {kindShortLabel(kind)}
    </span>
  );
}
