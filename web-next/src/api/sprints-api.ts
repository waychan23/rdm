// Sprint endpoints: the project list, the detail drawer, allocation and the
// start/close lifecycle.

import { api } from "../lib/api";
import type { Sprint, SprintDetail } from "../types";
import { encode } from "./query";

export interface SprintInput {
  name: string;
  goal_md: string;
  start_date: string | null;
  end_date: string | null;
}

export function listProjectSprints(projectKey: string): Promise<Sprint[]> {
  return api
    .get<Sprint[]>(`/projects/${encode(projectKey)}/sprints`)
    .then((res) => res.data);
}

export function createSprint(projectKey: string, values: SprintInput): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/sprints`, values)
    .then(() => undefined);
}

export function getSprintDetail(sprintId: string): Promise<SprintDetail> {
  return api
    .get<SprintDetail>(`/sprints/${encode(sprintId)}`)
    .then((res) => res.data);
}

export function updateSprint(sprintId: string, values: SprintInput): Promise<void> {
  return api.patch(`/sprints/${encode(sprintId)}`, values).then(() => undefined);
}

export function addSprintItems(sprintId: string, displayIds: string[]): Promise<void> {
  return api
    .post(`/sprints/${encode(sprintId)}/items`, { items: displayIds })
    .then(() => undefined);
}

export function removeSprintItem(sprintId: string, displayId: string): Promise<void> {
  return api
    .del(`/sprints/${encode(sprintId)}/items/${encode(displayId)}`)
    .then(() => undefined);
}

export function startSprint(sprintId: string): Promise<void> {
  return api.post(`/sprints/${encode(sprintId)}/start`, {}).then(() => undefined);
}

export function closeSprint(sprintId: string): Promise<void> {
  return api.post(`/sprints/${encode(sprintId)}/close`, {}).then(() => undefined);
}
