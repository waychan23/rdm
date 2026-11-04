// Attachments and artifacts: project-scoped uploads, per-item listings, binary
// downloads (Bearer-protected) and artifact links.

import { api } from "../lib/api";
import type { Artifact, Attachment } from "../types";
import { encode } from "./query";

export function listWorkItemAttachments(
  projectKey: string,
  itemId: string,
): Promise<Attachment[]> {
  return api
    .get<Attachment[]>(
      `/projects/${encode(projectKey)}/attachments?owner_type=work_item&owner_ref=${encode(itemId)}`,
    )
    .then((res) => res.data);
}

/** Upload a project-scoped attachment; progress is reported when requested. */
export function uploadProjectAttachment(
  projectKey: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<Attachment> {
  const path = `/projects/${encode(projectKey)}/attachments`;
  const request = onProgress
    ? api.uploadWithProgress<Attachment>(path, form, onProgress)
    : api.upload<Attachment>(path, form);
  return request.then((res) => res.data);
}

export function deleteAttachment(attachmentId: string): Promise<void> {
  return api.del(`/attachments/${encode(attachmentId)}`).then(() => undefined);
}

export function downloadAttachment(downloadUrl: string, filename: string): Promise<void> {
  return api.download(downloadUrl, filename);
}

export function fetchAttachmentBlob(downloadUrl: string): Promise<Blob> {
  return api.fetchBlob(downloadUrl);
}

/** Protected binary as a revocable object URL (for markdown images). */
export function attachmentBlobUrl(downloadUrl: string): Promise<string> {
  return api.blobUrl(downloadUrl);
}

export function listWorkItemArtifacts(
  projectKey: string,
  itemId: string,
): Promise<Artifact[]> {
  return api
    .get<Artifact[]>(
      `/projects/${encode(projectKey)}/artifacts?owner_type=work_item&owner_ref=${encode(itemId)}`,
    )
    .then((res) => res.data);
}

export function createProjectArtifact(
  projectKey: string,
  payload: {
    owner_type: string;
    owner_ref: string;
    kind: string;
    label: string;
    url: string;
    description_md: string;
  },
): Promise<Artifact> {
  return api
    .post<Artifact>(`/projects/${encode(projectKey)}/artifacts`, payload)
    .then((res) => res.data);
}

export function deleteArtifact(artifactId: string): Promise<void> {
  return api.post(`/artifacts/${encode(artifactId)}/delete`, {}).then(() => undefined);
}
