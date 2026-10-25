// Minimal API client. In production the page is served from the same origin
// and loopback requests act as the bootstrap owner (architecture §16.33).

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

async function parse(res: Response): Promise<unknown> {
  if (res.status === 204) return {};
  const text = await res.text();
  return text ? JSON.parse(text) : {};
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await parse(res);
  if (!res.ok) {
    const err = ((payload as { error?: ApiError })?.error ?? {
      code: "ERROR",
      message: `HTTP ${res.status}`,
      details: {},
    }) as ApiError;
    throw new Error(`${err.code}: ${err.message}`, { cause: err });
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

  // Multipart upload: do not set Content-Type (the browser adds the boundary).
  async upload<T>(path: string, form: FormData): Promise<Envelope<T>> {
    const res = await fetch(`/api/v1${path}`, { method: "POST", body: form });
    const payload = await parse(res);
    if (!res.ok) {
      const err = ((payload as { error?: ApiError })?.error ?? {
        code: "ERROR",
        message: `HTTP ${res.status}`,
        details: {},
      }) as ApiError;
      throw new Error(`${err.code}: ${err.message}`, { cause: err });
    }
    return payload as Envelope<T>;
  },

  // Download through fetch so a future Authorization header can be attached;
  // saves the blob under the filename offered by the caller.
  async download(downloadUrl: string, filename: string): Promise<void> {
    const path = downloadUrl.startsWith("/api/v1")
      ? downloadUrl.slice("/api/v1".length)
      : downloadUrl;
    const res = await fetch(`/api/v1${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};

/** Gate/validation hints carried by 409 responses, if present. */
export function errorCause(e: unknown): ApiError | undefined {
  return (e as { cause?: ApiError })?.cause;
}
