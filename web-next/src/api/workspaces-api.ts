// Project workspaces (repository / environment links).

import { api } from "../lib/api";
import type { Workspace } from "../types";
import { encode } from "./query";

export interface WorkspaceInput {
  name: string;
  kind: string;
  url: string;
  description_md: string | null;
}

export function listWorkspaces(projectKey: string): Promise<Workspace[]> {
  return api
    .get<Workspace[]>(`/projects/${encode(projectKey)}/workspaces`)
    .then((res) => res.data);
}

export function createWorkspace(
  projectKey: string,
  payload: WorkspaceInput,
): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/workspaces`, payload)
    .then(() => undefined);
}

export function updateWorkspace(
  workspaceId: string,
  payload: WorkspaceInput,
): Promise<void> {
  return api
    .patch(`/workspaces/${encode(workspaceId)}`, payload)
    .then(() => undefined);
}

export function deleteWorkspace(workspaceId: string): Promise<void> {
  return api.del(`/workspaces/${encode(workspaceId)}`).then(() => undefined);
}
