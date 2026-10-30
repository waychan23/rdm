// Shared state produced by global-setup.ts and consumed by the specs.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export const E2E_DIR = path.resolve(HERE, "..");
export const AUTH_DIR = path.join(E2E_DIR, ".auth");
export const CONTEXT_FILE = path.join(AUTH_DIR, "context.json");
export const SERVER_LOG = path.join(AUTH_DIR, "server.log");

export type UserName = "owner" | "alice" | "bob" | "carol";

export interface Session {
  id: string;
  name: string;
  password: string;
  accessToken: string;
  refreshToken: string;
}

export interface E2EContext {
  baseURL: string;
  projectKey: string;
  dataDir: string;
  owner: Session;
  users: Record<Exclude<UserName, "owner">, Session>;
}

export function storageStateFor(name: UserName): string {
  return path.join(AUTH_DIR, `${name}.json`);
}

export function loadContext(): E2EContext {
  if (!fs.existsSync(CONTEXT_FILE)) {
    throw new Error(
      `e2e context missing at ${CONTEXT_FILE}. ` +
        "Run `pnpm -C web-next e2e` (global setup boots the server and seeds data).",
    );
  }
  return JSON.parse(fs.readFileSync(CONTEXT_FILE, "utf8")) as E2EContext;
}
