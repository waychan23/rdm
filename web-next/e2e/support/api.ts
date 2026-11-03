// Deterministic REST setup for browser specs.
//
// The browser tests always *drive* workflow actions through the UI; this client
// only creates the preconditions (project, people, items, prior statuses) and
// reads state back for assertions. It also implements the first-party OAuth
// login so global setup can mint browser tokens for each seeded identity.
import { createHash, randomBytes } from "node:crypto";

import type { E2EContext, Session, UserName } from "./context";

export const OWNER_PASSWORD = "OwnerPass123";
export const USER_PASSWORD = "MemberPass123";

interface Envelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export interface StepDef {
  key: string;
  name: string;
  to: string;
  mode: "direct" | "approval" | "task";
  note: "optional" | "required";
  gates?: Record<string, unknown>;
  tasks?: { type: string; title: string; complete_on: string } | null;
}

export interface KindDef {
  states: string[];
  terminal: string[];
  steps?: Record<string, StepDef[]>;
  subtypes?: Record<string, KindDef>;
}

export interface WorkflowDto {
  version: number;
  kinds: Record<string, KindDef>;
}

export interface Item {
  id: string;
  display_id: string;
  kind: string;
  task_type?: string | null;
  title: string;
  status: string;
  row_version: number;
  assignee?: { id: string; name: string } | null;
  reviewer?: { id: string; name: string }[];
  custom_fields?: Record<string, unknown> | null;
}

export interface ItemDetail {
  data: Item;
  meta: {
    available_steps?: StepDef[];
    active_step?: { id: string; name: string; status: string; executors: unknown[] } | null;
    parent?: Item | null;
    children?: Item[];
  };
}

export interface CreateItemSeed {
  kind: "epic" | "story" | "issue" | "task";
  title: string;
  task_type?: string;
  priority?: number;
  parent?: string;
  assignee?: UserName;
  participants?: UserName[];
  reviewer?: UserName[];
  review_content_md?: string | null;
  custom_fields?: Record<string, unknown>;
  planned_start_date?: string;
  planned_end_date?: string;
  /** Reach this status through direct steps before returning. Requires assignee. */
  status?: string;
}

function base64url(bytes: Buffer): string {
  return bytes.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pkce(): { verifier: string; challenge: string } {
  const verifier = base64url(randomBytes(48));
  const challenge = base64url(createHash("sha256").update(verifier).digest());
  return { verifier, challenge };
}

async function readJson(res: Response): Promise<any> {
  const text = await res.text();
  return text ? JSON.parse(text) : {};
}

export async function oauthLogin(
  baseURL: string,
  name: string,
  password: string,
): Promise<{ accessToken: string; refreshToken: string }> {
  const { verifier, challenge } = pkce();
  const redirectURI = `${baseURL}/auth/callback`;
  const authorize = new URL("/api/oauth/authorize", baseURL);
  authorize.search = new URLSearchParams({
    response_type: "code",
    client_id: "rdm-web",
    redirect_uri: redirectURI,
    state: "e2e",
    code_challenge: challenge,
    code_challenge_method: "S256",
    scope: "web",
  }).toString();

  const authorizeRes = await fetch(authorize, { redirect: "manual" });
  const loginLocation = authorizeRes.headers.get("location");
  if (authorizeRes.status !== 302 || !loginLocation) {
    throw new Error(`GET /api/oauth/authorize -> ${authorizeRes.status} (${loginLocation})`);
  }
  const authKey = new URL(loginLocation, baseURL).searchParams.get("auth_key");
  if (!authKey) throw new Error(`no auth_key in ${loginLocation}`);

  const loginRes = await fetch(new URL("/api/v1/auth/login", baseURL), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auth_key: authKey, name, password, remember: true }),
  });
  const login = await readJson(loginRes);
  if (!loginRes.ok) throw new Error(`login ${name} failed: ${JSON.stringify(login)}`);
  const redirectTo = login.data?.redirect_to as string | undefined;
  if (!redirectTo) throw new Error(`login ${name} returned no redirect: ${JSON.stringify(login)}`);
  const code = new URL(redirectTo, baseURL).searchParams.get("code");
  if (!code) throw new Error(`no code in redirect ${redirectTo}`);

  const tokenRes = await fetch(new URL("/api/oauth/token", baseURL), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      code_verifier: verifier,
      client_id: "rdm-web",
      redirect_uri: redirectURI,
    }).toString(),
  });
  const tokens = await readJson(tokenRes);
  if (!tokenRes.ok) throw new Error(`token exchange for ${name} failed: ${JSON.stringify(tokens)}`);
  if (tokens.scope !== "web") throw new Error(`unexpected scope ${tokens.scope}`);
  return { accessToken: tokens.access_token, refreshToken: tokens.refresh_token };
}

export class Api {
  constructor(private readonly ctx: E2EContext) {}

  token(name: UserName = "owner"): string {
    return name === "owner" ? this.ctx.owner.accessToken : this.ctx.users[name].accessToken;
  }

  userId(name: UserName): string {
    return name === "owner" ? this.ctx.owner.id : this.ctx.users[name].id;
  }

  async request<T>(
    method: string,
    path: string,
    body?: unknown,
    actor: UserName = "owner",
  ): Promise<Envelope<T>> {
    const url = new URL(`/api/v1${path}`, this.ctx.apiURL ?? this.ctx.baseURL);
    const res = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${this.token(actor)}`,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const payload = await readJson(res);
    if (!res.ok) {
      throw new Error(`${method} ${path} -> ${res.status}: ${JSON.stringify(payload)}`);
    }
    return payload as Envelope<T>;
  }

  get<T>(path: string, actor: UserName = "owner") {
    return this.request<T>("GET", path, undefined, actor);
  }

  post<T>(path: string, body: unknown = {}, actor: UserName = "owner") {
    return this.request<T>("POST", path, body, actor);
  }

  workflow(projectKey = this.ctx.projectKey): Promise<WorkflowDto> {
    return this.get<WorkflowDto>(
      `/workflow?project=${encodeURIComponent(projectKey)}`,
    ).then((res) => res.data);
  }

  getItem(ref: string, actor: UserName = "owner"): Promise<ItemDetail> {
    return this.get<Item>(`/work-items/${encodeURIComponent(ref)}`, actor);
  }

  async createProject(key: string, name = key): Promise<void> {
    await this.post("/projects", {
      key,
      name,
      ...(this.ctx.workflowConfigVersionId
        ? { workflow_config_version_id: this.ctx.workflowConfigVersionId }
        : {}),
    });
  }

  async addMember(projectKey: string, user: UserName, roles = ["worker"]): Promise<void> {
    await this.post(`/projects/${projectKey}/members`, {
      user_id: this.userId(user),
      roles,
    });
  }

  /** Fresh project for specs that must not see rows accumulated by others. */
  async createSandboxProject(members: UserName[] = ["alice"]): Promise<string> {
    const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 36).toString(36)}`
      .toUpperCase()
      .slice(-9);
    const key = `D${suffix}`;
    await this.createProject(key, "E2E Sandbox");
    for (const member of members) await this.addMember(key, member);
    return key;
  }

  async createItem(seed: CreateItemSeed, actor: UserName = "owner"): Promise<Item> {
    return this.createItemIn(this.ctx.projectKey, seed, actor);
  }

  async createItemIn(
    projectKey: string,
    seed: CreateItemSeed,
    actor: UserName = "owner",
  ): Promise<Item> {
    const payload: Record<string, unknown> = {
      kind: seed.kind,
      title: seed.title,
    };
    if (seed.task_type) payload.task_type = seed.task_type;
    if (seed.priority !== undefined) payload.priority = seed.priority;
    if (seed.parent) payload.parent = seed.parent;
    if (seed.assignee) payload.assignee = this.userId(seed.assignee);
    if (seed.participants?.length) {
      payload.participants = seed.participants.map((name) => this.userId(name));
    }
    if (seed.reviewer?.length) payload.reviewer = seed.reviewer.map((name) => this.userId(name));
    if (seed.review_content_md !== undefined) payload.review_content_md = seed.review_content_md;
    if (seed.custom_fields !== undefined) payload.custom_fields = seed.custom_fields;
    if (seed.planned_start_date) payload.planned_start_date = seed.planned_start_date;
    if (seed.planned_end_date) payload.planned_end_date = seed.planned_end_date;
    const created = (await this.post<Item>(`/projects/${projectKey}/work-items`, payload, actor))
      .data;
    if (seed.status && seed.status !== created.status) {
      if (!seed.assignee) {
        throw new Error("CreateItemSeed.status requires an assignee for direct-step setup");
      }
      return this.advanceTo(created, seed.status, seed.assignee);
    }
    return created;
  }

  /** Walk the direct-step graph to reach a precondition status. */
  async advanceTo(item: Item, target: string, actor: UserName): Promise<Item> {
    const workflow = await this.workflow();
    const kind = this.resolveKind(workflow, item.kind, item.task_type ?? null);
    let current = item;
    for (let guard = 0; guard < 12; guard += 1) {
      if (current.status === target) return current;
      const path = findDirectPath(kind, current.status, target);
      if (!path || path.length === 0) {
        throw new Error(`no direct path ${item.kind}/${item.task_type ?? "-"}: ${current.status} -> ${target}`);
      }
      const next = path[0];
      const detail = await this.getItem(current.id, actor);
      if (detail.data.status !== current.status) {
        current = detail.data;
        continue;
      }
      await this.post(
        `/work-items/${detail.data.display_id}/steps/${next.key}`,
        {
          row_version: detail.data.row_version,
          note_md: next.note === "required" ? "e2e setup note" : null,
        },
        actor,
      );
      current = (await this.getItem(current.id, actor)).data;
    }
    throw new Error(`failed to reach ${target} from ${item.status}`);
  }

  private resolveKind(workflow: WorkflowDto, kind: string, taskType: string | null): KindDef {
    const base = workflow.kinds[kind];
    if (!base) throw new Error(`unknown kind ${kind}`);
    if (kind === "task" && taskType && base.subtypes?.[taskType]) {
      return { ...base, ...base.subtypes[taskType] };
    }
    return base;
  }
}

function findDirectPath(kind: KindDef, from: string, to: string): StepDef[] | null {
  const queue: Array<{ state: string; path: StepDef[] }> = [{ state: from, path: [] }];
  const seen = new Set([from]);
  while (queue.length > 0) {
    const { state, path } = queue.shift()!;
    if (state === to) return path;
    for (const step of kind.steps?.[state] ?? []) {
      if (step.mode !== "direct" || seen.has(step.to)) continue;
      seen.add(step.to);
      queue.push({ state: step.to, path: [...path, step] });
    }
  }
  return null;
}
