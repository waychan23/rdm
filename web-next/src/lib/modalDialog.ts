/**
 * Whether an Atlaskit modal dialog is open anywhere above the page.
 *
 * The work item drawer defers to it (RDM-162): while a dialog is open, Escape
 * and blank-backdrop clicks belong to the dialog and must not also dismiss the
 * drawer underneath it.
 */
export function hasOpenModalDialog(): boolean {
  return document.querySelector('[role="dialog"]') !== null;
}
