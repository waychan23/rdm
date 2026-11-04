import { apiUrl } from "../lib/api";

/** Authenticated SSE endpoint; EventSource cannot send the Bearer header. */
export function streamUrl(since: string | null): string {
  const params = new URLSearchParams();
  if (since) params.set("since", since);
  return apiUrl(`/stream?${params.toString()}`);
}
