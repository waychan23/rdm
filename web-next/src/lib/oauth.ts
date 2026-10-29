// Stateless OAuth 2.1 (Authorization Code + PKCE) against the first-party
// `rdm-web` client (§17). There is no session cookie; access/refresh tokens
// live in localStorage.

const ACCESS_KEY = "rdm.access";
const REFRESH_KEY = "rdm.refresh";
const EXPIRES_KEY = "rdm.expires_at";
const VERIFIER_KEY = "rdm.pkce_verifier";
const STATE_KEY = "rdm.pkce_state";
const POST_LOGIN_KEY = "rdm.post_login";

const CLIENT_ID = "rdm-web";
const SCOPE = "mcp";

export interface TokenSet {
  accessToken: string;
  refreshToken: string;
  expiresAt: number; // epoch ms
}

function base64url(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(bytes = 32): string {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return base64url(buf);
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

export function callbackUrl(): string {
  return `${window.location.origin}/auth/callback`;
}

// Auth-flow pages are never valid post-login destinations: landing back on
// /login (no auth_key) immediately starts another authorization request, which
// loops forever after logout. Anything that is not a normal SPA page falls
// back to /projects.
const AUTH_PAGE_PREFIXES = ["/login", "/auth/", "/set-password", "/oauth/consent"];

export function safePostLoginPath(target: string | null | undefined): string {
  if (!target) return "/projects";
  if (!target.startsWith("/") || target.startsWith("//") || target.startsWith("/\\")) {
    return "/projects";
  }
  const path = target.split("?")[0].split("#")[0];
  if (AUTH_PAGE_PREFIXES.some((prefix) => path === prefix || path.startsWith(prefix))) {
    return "/projects";
  }
  return target;
}

/** Start the full-page OAuth flow, remembering where to return afterwards. */
export async function beginLogin(postLoginPath?: string): Promise<void> {
  const verifier = randomString(48);
  const state = randomString(16);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(
    POST_LOGIN_KEY,
    safePostLoginPath(postLoginPath ?? window.location.pathname + window.location.search),
  );
  const params = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_ID,
    redirect_uri: callbackUrl(),
    scope: SCOPE,
    state,
    code_challenge: await challengeFor(verifier),
    code_challenge_method: "S256",
  });
  window.location.assign(`/authorize?${params.toString()}`);
}

export function takePostLoginPath(): string {
  const path = sessionStorage.getItem(POST_LOGIN_KEY);
  sessionStorage.removeItem(POST_LOGIN_KEY);
  return safePostLoginPath(path);
}

/** Exchange the callback code; returns false when state/PKCE checks fail. */
export async function completeLogin(code: string, state: string): Promise<boolean> {
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  const expectedState = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  if (!verifier || state !== expectedState) return false;

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    client_id: CLIENT_ID,
    redirect_uri: callbackUrl(),
    code_verifier: verifier,
  });
  const res = await fetch("/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) return false;
  storeTokens((await res.json()) as RawTokenResponse);
  return true;
}

interface RawTokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
}

export function storeTokens(raw: RawTokenResponse): void {
  localStorage.setItem(ACCESS_KEY, raw.access_token);
  if (raw.refresh_token) localStorage.setItem(REFRESH_KEY, raw.refresh_token);
  localStorage.setItem(EXPIRES_KEY, String(Date.now() + raw.expires_in * 1000));
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(EXPIRES_KEY);
}

let refreshInFlight: Promise<boolean> | null = null;

/** Single-flight refresh; concurrent 401s share one token request. */
export function refreshTokens(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    const refresh = getRefreshToken();
    if (!refresh) return false;
    const body = new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refresh,
      client_id: CLIENT_ID,
    });
    const res = await fetch("/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) {
      clearTokens();
      return false;
    }
    storeTokens((await res.json()) as RawTokenResponse);
    return true;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}
