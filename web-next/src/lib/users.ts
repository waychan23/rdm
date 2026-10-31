/** Presentation helpers for user identities (§17.116). */

/** Minimal shape of a user reference returned by the API. */
export interface UserLabelRef {
  name?: string | null;
  display_name?: string | null;
}

/** Reader-facing name: display_name when set, else the login name. */
export function userLabel(user: UserLabelRef | null | undefined): string {
  if (!user) return "";
  return user.display_name || user.name || "";
}
