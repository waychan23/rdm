// A detail drawer that is already open must not replay its enter animation
// when it is re-mounted behind (or after) the work item drawer. Suppression is
// keyed by drawer family ("sprint" / "release") and communicated to CSS through
// a token list on <html>.
const ATTRIBUTE = "data-rdm-restored-drawer";
const suppressed = new Set<string>();

function sync(): void {
  const root = document.documentElement;
  if (suppressed.size === 0) root.removeAttribute(ATTRIBUTE);
  else root.setAttribute(ATTRIBUTE, [...suppressed].join(" "));
}

/** The drawer is already visible; skip its enter animation on the next mount. */
export function suppressDrawerEnter(key: string): void {
  suppressed.add(key);
  sync();
}

/** A user opened/closed the drawer explicitly, so normal motion resumes. */
export function allowDrawerEnter(key: string): void {
  suppressed.delete(key);
  sync();
}
