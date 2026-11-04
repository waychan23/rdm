// Work item read/write endpoints, including comments, child links and the
// named workflow steps that move an item through the state machine.

import { api, type Envelope } from "../lib/api";
import type {
  ActiveStep,
  Assignee,
  Comment,
  HistoryEntry,
  Sprint,
  WorkItem,
} from "../types";
import { encode, withQuery, type Query } from "./query";

export interface FilterOptions {
  statuses: string[];
  assignees: Assignee[];
  participants: Assignee[];
}

export interface WorkItemStepPayload {
  row_version?: number;
  note_md?: string | null;
  attachment_ids?: string[];
  executors?: string[];
}

export interface StepExecutePayload {
  note_md: string | null;
  attachment_ids: string[];
}

export interface StepReassignPayload {
  row_version: number;
  executors: string[];
}

export interface StepRejectPayload {
  row_version: number;
  reason: string;
}

export function listWorkItems(
  projectKey: string,
  query?: Query,
): Promise<Envelope<WorkItem[]>> {
  return api.get<WorkItem[]>(withQuery(`/projects/${encode(projectKey)}/work-items`, query));
}

export function getFilterOptions(
  projectKey: string,
  query?: Query,
): Promise<FilterOptions> {
  return api
    .get<FilterOptions>(
      withQuery(`/projects/${encode(projectKey)}/work-items/filter-options`, query),
    )
    .then((res) => res.data);
}

export function createWorkItem(
  projectKey: string,
  payload: Record<string, unknown>,
): Promise<WorkItem> {
  return api
    .post<WorkItem>(`/projects/${encode(projectKey)}/work-items`, payload)
    .then((res) => res.data);
}

export function getWorkItem(id: string): Promise<Envelope<WorkItem>> {
  return api.get<WorkItem>(`/work-items/${encode(id)}`);
}

export function updateWorkItem(
  id: string,
  payload: Record<string, unknown>,
): Promise<WorkItem> {
  return api.patch<WorkItem>(`/work-items/${encode(id)}`, payload).then((res) => res.data);
}

export function reparentWorkItem(
  id: string,
  parent: string | null,
  rowVersion: number,
): Promise<WorkItem> {
  return api
    .post<WorkItem>(`/work-items/${encode(id)}/reparent`, {
      parent,
      row_version: rowVersion,
    })
    .then((res) => res.data);
}

export function assignWorkItem(id: string, memberId: string): Promise<void> {
  return api
    .post(`/work-items/${encode(id)}/assign`, { member: memberId })
    .then(() => undefined);
}

export function deleteWorkItem(id: string): Promise<void> {
  return api.del(`/work-items/${encode(id)}`).then(() => undefined);
}

export function getWorkItemHistory(
  id: string,
  query?: Query,
): Promise<Envelope<HistoryEntry[]>> {
  return api.get<HistoryEntry[]>(
    withQuery(`/work-items/${encode(id)}/history`, query),
  );
}

export function getWorkItemSprint(id: string): Promise<{ sprint: Sprint | null }> {
  return api
    .get<{ sprint: Sprint | null }>(`/work-items/${encode(id)}/sprint`)
    .then((res) => res.data);
}

export function listWorkItemComments(
  id: string,
  options: { limit: number; offset: number },
): Promise<Envelope<Comment[]>> {
  return api.get<Comment[]>(
    `/work-items/${encode(id)}/comments?limit=${options.limit}&offset=${options.offset}`,
  );
}

export function createWorkItemComment(
  id: string,
  payload: { body_md: string; reply_to_id: string | null; attachment_ids: string[] },
): Promise<Comment> {
  return api
    .post<Comment>(`/work-items/${encode(id)}/comments`, payload)
    .then((res) => res.data);
}

export function updateComment(id: string, bodyMd: string): Promise<void> {
  return api.patch(`/comments/${encode(id)}`, { body_md: bodyMd }).then(() => undefined);
}

export function deleteComment(id: string): Promise<void> {
  return api.del(`/comments/${encode(id)}`).then(() => undefined);
}

/**
 * POST /work-items/{id}/steps/{key}: runs a direct step or starts a named
 * approval/task step, depending on the workflow definition.
 */
export function runWorkItemStep(
  itemId: string,
  stepKey: string,
  payload: WorkItemStepPayload,
): Promise<void> {
  return api
    .post(`/work-items/${encode(itemId)}/steps/${encode(stepKey)}`, payload)
    .then(() => undefined);
}

export function executeStepInstance(
  stepId: string,
  payload: StepExecutePayload,
): Promise<void> {
  return api
    .post(`/work-item-steps/${encode(stepId)}/execute`, payload)
    .then(() => undefined);
}

export function reassignStepInstance(
  stepId: string,
  payload: StepReassignPayload,
): Promise<void> {
  return api
    .post(`/work-item-steps/${encode(stepId)}/reassign`, payload)
    .then(() => undefined);
}

export function cancelStepInstance(step: ActiveStep): Promise<void> {
  return api
    .post(`/work-item-steps/${encode(step.id)}/cancel`, {
      row_version: step.row_version,
    })
    .then(() => undefined);
}

export function rejectStepInstance(step: ActiveStep, reason: string): Promise<void> {
  const payload: StepRejectPayload = { row_version: step.row_version, reason };
  return api
    .post(`/work-item-steps/${encode(step.id)}/reject`, payload)
    .then(() => undefined);
}

export function retryStepInstance(step: ActiveStep): Promise<void> {
  return api
    .post(`/work-item-steps/${encode(step.id)}/retry`, {
      row_version: step.row_version,
    })
    .then(() => undefined);
}
