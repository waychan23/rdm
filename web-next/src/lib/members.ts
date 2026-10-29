import type { OrgUser, ProjectMemberRow } from "../types";

/** Flatten the folded members response (humans + their agents) to one list. */
export function flattenMembers(rows: ProjectMemberRow[]): OrgUser[] {
  const out: OrgUser[] = [];
  for (const row of rows) {
    out.push(row);
    for (const agent of row.agents ?? []) out.push(agent.user);
  }
  return out;
}
