// Minimal API client. In production the page is served from the same origin
// and loopback requests act as the bootstrap owner (architecture §16.33).

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await res.json();
  if (!res.ok) {
    const err = (payload?.error ?? {
      code: "ERROR",
      message: `HTTP ${res.status}`,
      details: {},
    }) as ApiError;
    throw new Error(`${err.code}: ${err.message}`);
  }
  return payload as T;
}

interface Envelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export const api = {
  get: <T>(path: string) => request<Envelope<T>>("GET", path),
  post: <T>(path: string, body?: unknown) =>
    request<Envelope<T>>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) =>
    request<Envelope<T>>("PATCH", path, body),
  del: <T>(path: string) => request<Envelope<T>>("DELETE", path),
};
