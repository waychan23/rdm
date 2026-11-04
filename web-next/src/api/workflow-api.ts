// Workflow definition lookup and workflow-config administration.

import { api } from "../lib/api";
import type { WorkflowConfig, WorkflowConfigVersion, WorkflowDto } from "../types";
import { encode } from "./query";

export function getWorkflow(projectKey: string): Promise<WorkflowDto> {
  return api
    .get<WorkflowDto>(`/workflow?project=${encode(projectKey)}`)
    .then((res) => res.data);
}

export function listWorkflowConfigs(enabledOnly = false): Promise<WorkflowConfig[]> {
  const query = enabledOnly ? "?enabled=true" : "";
  return api.get<WorkflowConfig[]>(`/workflow-configs${query}`).then((res) => res.data);
}

export function getWorkflowConfig(key: string): Promise<WorkflowConfig> {
  return api
    .get<WorkflowConfig>(`/workflow-configs/${encode(key)}`)
    .then((res) => res.data);
}

export function getWorkflowConfigVersion(versionId: string): Promise<WorkflowConfigVersion> {
  return api
    .get<WorkflowConfigVersion>(`/workflow-configs/versions/${encode(versionId)}`)
    .then((res) => res.data);
}

export function createWorkflowConfigVersion(
  key: string,
  payload: { content_text: string; base_version_id: string },
): Promise<{ created: boolean; version: WorkflowConfigVersion }> {
  return api
    .post<{ created: boolean; version: WorkflowConfigVersion }>(
      `/workflow-configs/${encode(key)}/versions`,
      payload,
    )
    .then((res) => res.data);
}

export function setWorkflowConfigEnabled(key: string, enabled: boolean): Promise<void> {
  return api
    .patch(`/workflow-configs/${encode(key)}`, { enabled })
    .then(() => undefined);
}

export function forkWorkflowConfig(
  key: string,
  payload: { key: string; name: string },
): Promise<void> {
  return api
    .post(`/workflow-configs/${encode(key)}/fork`, payload)
    .then(() => undefined);
}
