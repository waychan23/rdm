import StatusLozenge from "../../workitems/status";

/** Sprint states reuse the work-item lozenge colours. */
export function sprintLozenge(status: string) {
  if (status === "ACTIVE") return <StatusLozenge status="IN_PROGRESS" />;
  if (status === "CLOSED") return <StatusLozenge status="DONE" />;
  return <StatusLozenge status="TODO" />;
}
