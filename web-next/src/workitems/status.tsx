import type { ReactNode } from "react";

import Lozenge from "@atlaskit/lozenge";
import type { NewLozengeProps } from "@atlaskit/lozenge";

// Mirrors the Vue StatusPill classification: blocked beats all, then known
// terminal states, then known to-do states; everything else is "in progress".
const DONE = ["DONE", "PUBLISHED", "CLOSED", "CANCELLED", "REJECTED", "COMPLETED"];
const TODO = ["TODO", "OPEN", "PLANNED", "BACKLOG", "NEW", "DRAFT"];

export type StatusTone = "todo" | "doing" | "done" | "blocked";

export function statusTone(status: string): StatusTone {
  const s = status.toUpperCase();
  if (s.includes("BLOCK")) return "blocked";
  if (DONE.some((d) => s === d || s.endsWith("_" + d))) return "done";
  if (TODO.includes(s)) return "todo";
  return "doing";
}

const APPEARANCE: Record<StatusTone, NewLozengeProps["appearance"]> = {
  doing: "inprogress", // bold blue
  blocked: "removed", // bold red
  done: "default", // neutral gray
  todo: "accent-blue", // subtle blue
};

export default function StatusLozenge({
  status,
  children,
}: {
  status: string;
  children?: ReactNode;
}) {
  return (
    <Lozenge
      appearance={APPEARANCE[statusTone(status)]}
      testId={`status-lozenge-${status}`}
    >
      {children ?? status}
    </Lozenge>
  );
}
