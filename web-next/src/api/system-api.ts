import { api } from "../lib/api";
import type { OrgSettings } from "../types";

/** Organization-wide system settings (RDM-127). */
export function getOrgSettings(): Promise<OrgSettings> {
  return api.get<OrgSettings>("/org-settings").then((res) => res.data);
}

export function updateOrgSettings(webOrigin: string | null): Promise<OrgSettings> {
  return api
    .patch<OrgSettings>("/org-settings", { web_origin: webOrigin })
    .then((res) => res.data);
}
