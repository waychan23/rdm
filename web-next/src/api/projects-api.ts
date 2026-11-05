// Project endpoints plus membership and the project overview.

import { api } from "../lib/api";
import type { Project, ProjectMemberRow, Release, WorkItem } from "../types";
import { encode } from "./query";

export interface OverviewSprint {
  id: string;
  name: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  total: number;
  done: number;
  percent: number;
  days_remaining: number | null;
  by_status: Record<string, number>;
}

/** Project landing page payload (RDM-185): counters + actionable lists. */
export interface ProjectOverview {
  project_key: string;
  project_name: string;
  project_status: string;
  project_description_md?: string | null;
  total_items: number;
  open_items: number;
  done_items: number;
  my_open_items: number;
  members: number;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  overdue_count: number;
  blocked_count: number;
  my_items: WorkItem[];
  overdue_items: WorkItem[];
  recent_items: WorkItem[];
  active_sprint: OverviewSprint | null;
  releases: Release[];
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
