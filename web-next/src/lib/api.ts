// Same-origin API client. Every request carries `Authorization: Bearer`; a
// 401 triggers one silent refresh through the OAuth refresh token, then a
// full-page login redirect if that fails (§17).

import { beginLogin, clearTokens, getAccessToken, refreshTokens } from "./oauth";

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

// Auth endpoints handle their own 401s (bad credentials, expired ticket).
// Letting the global handler react would clear a valid session and bounce the
// page — e.g. "wrong old password" would trigger a full re-login instead of an
// inline error, and logout could start a fresh authorization request.
function isAuthPath(path: string): boolean {
  return path.startsWith("/auth/") || path.startsWith("/oauth/consent");
}

async function kickToLogin() {
  clearTokens();
  if (window.location.pathname !== "/login") {
    await beginLogin();
  }
}

function errorFrom(payload: unknown, status: number): ApiError {
  return (
    (payload as { error?: ApiError })?.error ?? {
      code: "ERROR",
      message: `HTTP ${status}`,
      details: {},
    }
  );
}

function requestHeaders(body: unknown, token: string | null): HeadersInit {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const send = (token: string | null) =>
    fetch(`/api/v1${path}`, {
      method,
      headers: requestHeaders(body, token),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

  let res = await send(getAccessToken());
  if (res.status === 401 && !isAuthPath(path)) {
    if (await refreshTokens()) {
      res = await send(getAccessToken());
    }
    if (res.status === 401) await kickToLogin();
  }
  const payload = await parse(res);
  if (!res.ok) throw new Error("API_ERROR", { cause: errorFrom(payload, res.status) });
  return payload as T;
}

interface Envelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export const api = {
  get: <T>(path: string) => request<Envelope<T>>("GET", path),
  post: <T>(path: string, body?: unknown) => request<Envelope<T>>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<Envelope<T>>("PUT", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<Envelope<T>>("PATCH", path, body),
  del: <T>(path: string) => request<Envelope<T>>("DELETE", path),

  // Multipart upload: do not set Content-Type (the browser adds the boundary).
  async upload<T>(path: string, form: FormData): Promise<Envelope<T>> {
    const send = (token: string | null) =>
      fetch(`/api/v1${path}`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: form,
      });
    let res = await send(getAccessToken());
    if (res.status === 401) {
      if (await refreshTokens()) res = await send(getAccessToken());
      if (res.status === 401) await kickToLogin();
    }
    const payload = await parse(res);
    if (!res.ok) throw new Error("API_ERROR", { cause: errorFrom(payload, res.status) });
    return payload as Envelope<T>;
  },

  download(downloadUrl: string, filename: string): Promise<void> {
    const path = downloadUrl.startsWith("/api/v1")
      ? downloadUrl.slice("/api/v1".length)
      : downloadUrl;
    return (async () => {
      const res = await fetch(`/api/v1${path}`, {
        headers: getAccessToken()
          ? { Authorization: `Bearer ${getAccessToken()}` }
          : undefined,
      });
      if (res.status === 401) {
        await kickToLogin();
        throw new Error("HTTP 401");
      }
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
    })();
  },
};

/** Gate/validation hints carried by error responses, if present. */
export function errorCause(e: unknown): ApiError | undefined {
  return (e as { cause?: ApiError })?.cause;
}
