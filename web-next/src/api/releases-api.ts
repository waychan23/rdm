// Release endpoints: project scope, detail drawer, item allocation and
// publish/cancel.

import { api } from "../lib/api";
import type { Release, ReleaseDetail } from "../types";
import { encode } from "./query";

export interface ReleaseInput {
  name: string;
  description_md: string;
  target_date: string | null;
}

export function listProjectReleases(projectKey: string): Promise<Release[]> {
  return api
    .get<Release[]>(`/projects/${encode(projectKey)}/releases`)
    .then((res) => res.data);
}

export function createRelease(projectKey: string, values: ReleaseInput): Promise<void> {
  return api
    .post(`/projects/${encode(projectKey)}/releases`, values)
    .then(() => undefined);
}

export function getReleaseDetail(releaseId: string): Promise<ReleaseDetail> {
  return api
    .get<ReleaseDetail>(`/releases/${encode(releaseId)}`)
    .then((res) => res.data);
}

export function updateRelease(releaseId: string, values: ReleaseInput): Promise<void> {
  return api.patch(`/releases/${encode(releaseId)}`, values).then(() => undefined);
}

export function addReleaseItems(releaseId: string, displayIds: string[]): Promise<void> {
  return api
    .post(`/releases/${encode(releaseId)}/items`, { items: displayIds })
    .then(() => undefined);
}

export function removeReleaseItem(releaseId: string, displayId: string): Promise<void> {
  return api
    .del(`/releases/${encode(releaseId)}/items/${encode(displayId)}`)
    .then(() => undefined);
}

export function publishRelease(releaseId: string): Promise<void> {
  return api.post(`/releases/${encode(releaseId)}/publish`, {}).then(() => undefined);
}

export function cancelRelease(releaseId: string): Promise<void> {
  return api.post(`/releases/${encode(releaseId)}/cancel`, {}).then(() => undefined);
}
