// Same-origin API client. Every request carries `Authorization: Bearer`; a
// 401 triggers one silent refresh through the OAuth refresh token, then a
// full-page login redirect if that fails (§17).

import { apiLocale, i18n } from "../i18n";
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
      message: i18n.t("error.httpStatus", { status }),
      details: {},
    }
  );
}

function requestHeaders(body: unknown, token: string | null): HeadersInit {
  const headers: Record<string, string> = { "Accept-Language": apiLocale() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

const TIMEOUT_MS = 15_000;

/**
 * Every request is bounded; a hung backend must surface as a retryable error
 * instead of an endless spinner. `AbortSignal.timeout` is supported by all
 * browsers we target (loopback-only internal tool).
 */
async function fetchWithTimeout(input: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(input, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") {
      throw new Error("API_ERROR", {
        cause: {
          code: "TIMEOUT",
          message: i18n.t("error.timeout", { seconds: TIMEOUT_MS / 1000 }),
          details: {},
        } satisfies ApiError,
      });
    }
    throw e;
  }
}

/** Absolute URL of a REST path (service modules pass `/work-items/...`). */
export function apiUrl(path: string): string {
  return `/api/v1${path}`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const send = (token: string | null) =>
    fetchWithTimeout(apiUrl(path), {
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

export interface Envelope<T> {
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
      fetchWithTimeout(apiUrl(path), {
        method: "POST",
        headers: {
          "Accept-Language": apiLocale(),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
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

  /** Multipart upload with progress (XHR is the only browser API exposing it). */
  uploadWithProgress<T>(
    path: string,
    form: FormData,
    onProgress: (percent: number) => void,
  ): Promise<Envelope<T>> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl(path));
      xhr.setRequestHeader("Accept-Language", apiLocale());
      const token = getAccessToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
      xhr.onerror = () => reject(new Error(i18n.t("error.uploadNetwork")));
      xhr.onload = () => {
        let payload: unknown = {};
        try {
          payload = xhr.responseText ? JSON.parse(xhr.responseText) : {};
        } catch {
          payload = {};
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload as Envelope<T>);
        } else {
          reject(new Error("API_ERROR", { cause: errorFrom(payload, xhr.status) }));
        }
      };
      xhr.send(form);
    });
  },

  download(downloadUrl: string, filename: string): Promise<void> {
    return (async () => {
      const blob = await api.fetchBlob(downloadUrl);
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

  /** Fetch a protected binary resource with the Bearer credential. */
  async fetchBlob(downloadUrl: string): Promise<Blob> {
    const path = downloadUrl.startsWith("/api/v1")
      ? downloadUrl.slice("/api/v1".length)
      : downloadUrl;
    const send = (token: string | null) =>
      fetchWithTimeout(apiUrl(path), {
        headers: {
          "Accept-Language": apiLocale(),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
    let res = await send(getAccessToken());
    if (res.status === 401) {
      if (await refreshTokens()) res = await send(getAccessToken());
      if (res.status === 401) await kickToLogin();
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.blob();
  },

  /** Fetch a protected binary resource and return a revocable object URL. */
  async blobUrl(downloadUrl: string): Promise<string> {
    const blob = await api.fetchBlob(downloadUrl);
    return URL.createObjectURL(blob);
  },
};

/** Gate/validation hints carried by error responses, if present. */
export function errorCause(e: unknown): ApiError | undefined {
  return (e as { cause?: ApiError })?.cause;
}
