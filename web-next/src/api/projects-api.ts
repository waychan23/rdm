// Project endpoints plus membership and the project overview.

import { api } from "../lib/api";
import type { Project, ProjectMemberRow } from "../types";
import { encode } from "./query";

export interface ProjectOverview {
  total_items: number;
  open_items: number;
  my_open_items: number;
  members: number;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
  active_sprint: {
    name: string;
    total: number;
    by_status: Record<string, number>;
  } | null;
}

export function listProjects(): Promise<Project[]> {
  return api.get<Project[]>("/projects").then((res) => res.data);
}

export function getProject(projectKey: string): Promise<Project> {
  return api.get<Project>(`/projects/${encode(projectKey)}`).then((res) => res.data);
}

export function createProject(payload: Record<string, unknown>): Promise<void> {
  return api.post("/projects", payload).then(() => undefined);
}

export function updateProject(
  projectKey: string,
  payload: Record<string, unknown>,
): Promise<void> {
  return api.patch(`/projects/${encode(projectKey)}`, payload).then(() => undefined);
}

export function transferProjectOwner(projectKey: string, userId: string): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/transfer-owner`, { user_id: userId })
    .then(() => undefined);
}

export function archiveProject(projectKey: string): Promise<void> {
  return api.post(`/projects/${encode(projectKey)}/archive`, {}).then(() => undefined);
}

export function getProjectOverview(projectKey: string): Promise<ProjectOverview> {
  return api
    .get<ProjectOverview>(`/projects/${encode(projectKey)}/overview`)
    .then((res) => res.data);
}

export function listProjectMembers(projectKey: string): Promise<ProjectMemberRow[]> {
  return api
    .get<ProjectMemberRow[]>(`/projects/${encode(projectKey)}/members`)
    .then((res) => res.data);
}

export function addProjectMember(
  projectKey: string,
  userId: string,
  roles: string[],
): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/members`, { user_id: userId, roles })
    .then(() => undefined);
}

export function updateProjectMember(
  projectKey: string,
  userId: string,
  roles: string[],
): Promise<void> {
  return api
    .patch(`/projects/${encode(projectKey)}/members/${encode(userId)}`, { roles })
    .then(() => undefined);
}

export function removeProjectMember(projectKey: string, userId: string): Promise<void> {
  return api
    .del(`/projects/${encode(projectKey)}/members/${encode(userId)}`)
    .then(() => undefined);
}
