// Boots a throwaway rdm server, provisions identities/project, and writes
// browser storage states. The workflow specs then run against the real SPA.
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Api, OWNER_PASSWORD, USER_PASSWORD, oauthLogin } from "./support/api";
import {
  AUTH_DIR,
  SERVER_LOG,
  storageStateFor,
  type E2EContext,
  type Session,
  type UserName,
} from "./support/context";

const PROJECT_KEY = "WFE2E";
const MEMBER_NAMES = ["alice", "bob", "carol"] as const;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

async function waitForHealth(baseURL: string, child: ChildProcess): Promise<void> {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`rdm serve exited early (${child.exitCode}); see ${SERVER_LOG}`);
    }
    try {
      const res = await fetch(`${baseURL}/healthz`);
      if (res.ok) return;
    } catch {
      // Not listening yet.
    }
    await sleep(200);
  }
  throw new Error(`rdm serve did not become healthy in 45s; see ${SERVER_LOG}`);
}

async function recoverOwner(baseURL: string): Promise<void> {
  const deadline = Date.now() + 20_000;
  let ticket: string | null = null;
  while (Date.now() < deadline) {
    const res = await fetch(`${baseURL}/api/v1/local/owner-recovery`, { method: "POST" });
    if (res.ok) {
      const payload = await res.json();
      const url = new URL(payload.data.set_password_url, baseURL);
      ticket = url.searchParams.get("ticket");
      break;
    }
    // Health can answer before the lifespan bootstrap commits the owner row.
    await sleep(200);
  }
  if (!ticket) throw new Error("owner-recovery endpoint never returned a ticket");
  const res = await fetch(`${baseURL}/api/v1/auth/set-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticket, new_password: OWNER_PASSWORD }),
  });
  if (!res.ok) throw new Error(`setting owner password failed: ${await res.text()}`);
}

function storageState(baseURL: string, session: Session) {
  return {
    cookies: [],
    origins: [
      {
        origin: baseURL,
        localStorage: [
          { name: "rdm.access", value: session.accessToken },
          { name: "rdm.refresh", value: session.refreshToken },
          { name: "rdm.expires_at", value: String(Date.now() + 55 * 60 * 1000) },
          { name: "rdm.locale", value: "zh-CN" },
        ],
      },
    ],
  };
}

interface CreatedUser {
  id: string;
  name: string;
  password_reset_url: string;
}

async function createUser(api: Api, name: string): Promise<CreatedUser> {
  const { data } = await api.post<{ user: { id: string; name: string }; password_reset_url: string }>(
    "/users",
    { name },
  );
  return {
    id: data.user.id,
    name: data.user.name,
    password_reset_url: data.password_reset_url,
  };
}

async function setPassword(baseURL: string, resetURL: string, password: string): Promise<void> {
  const ticket = new URL(resetURL, baseURL).searchParams.get("ticket");
  if (!ticket) throw new Error(`no ticket in ${resetURL}`);
  const res = await fetch(`${baseURL}/api/v1/auth/set-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticket, new_password: password }),
  });
  if (!res.ok) throw new Error(`set-password failed: ${await res.text()}`);
}

function stopServer(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (child.exitCode !== null) {
      resolve();
      return;
    }
    const finish = () => resolve();
    child.once("exit", finish);
    // `uv run` may spawn a child process; detached puts both in one group.
    try {
      process.kill(-child.pid!, "SIGTERM");
    } catch {
      child.kill("SIGTERM");
    }
    setTimeout(() => {
      try {
        process.kill(-child.pid!, "SIGKILL");
      } catch {
        // Already gone.
      }
      resolve();
    }, 8_000).unref();
  });
}

interface WorkflowConfigSummary {
  key: string;
  active_version: { id: string; content_text: string } | null;
}

interface WorkflowConfigVersion {
  id: string;
  version: number;
  content_text: string;
}

/**
 * E2E workflow contract (RDM-84).
 *
 * The shipped default config is a product decision (minimal review flow), while
 * these specs exercise the engine's richer approval/task-mode/custom-field
 * features. Fork the builtin into an e2e-only config and pin every e2e project
 * to its active version, exactly as a real project would.
 */
async function createE2EWorkflowConfig(api: Api): Promise<string> {
  const configs = (await api.get<WorkflowConfigSummary[]>("/workflow-configs")).data;
  const builtin = configs.find((config) => config.key === "default");
  if (!builtin?.active_version) {
    throw new Error("builtin workflow config 'default' is missing");
  }

  const forked = (
    await api.post<{ config: { key: string }; version: WorkflowConfigVersion }>(
      "/workflow-configs/default/fork",
      { key: "e2e", name: "E2E Workflow" },
    )
  ).data;

  const raw = JSON.parse(forked.version.content_text) as Record<string, any>;
  // Task base flow: full dev flow with TO_REVIEW + CODE_REVIEW.
  raw.kinds.task.use = "dev_standard";
  const dev = raw.workflow_defs.dev_standard;
  dev.fields = { ...(dev.fields ?? {}), reviewer: true, review_content: true };

  const reviewSteps = dev.steps.TO_REVIEW as Array<Record<string, any>>;
  const codeReview = reviewSteps.find((step) => step.key === "CODE_REVIEW");
  if (!codeReview) throw new Error("dev_standard CODE_REVIEW step is missing");
  // Assignee + explicit reviewers only: project members must not become
  // candidates implicitly (spec 03 checks an unassigned reviewer cannot execute).
  codeReview.actors = ["assignee", "reviewers"];
  codeReview.gates = { ...(codeReview.gates ?? {}), required_fields: ["review_content"] };

  // Task-mode variant used by spec 05: one subtask per executor.
  reviewSteps.splice(reviewSteps.indexOf(codeReview) + 1, 0, {
    key: "CODE_REVIEW_TASKS",
    name: "Code Review Task",
    name_en: "Code Review Task",
    to: "DONE",
    mode: "task",
    actors: ["assignee"],
    executors: { min: 1, max: 1 },
    note: "optional",
    tasks: {
      type: "code_review",
      title: "Code Review: {display_id} {title}",
      complete_on: "DONE",
    },
  });

  // code_review subtype: IN_REVIEW graph + custom fields used by specs 05/07.
  const subtype = raw.kinds.task.subtypes.code_review;
  subtype.states = ["TODO", "IN_PROGRESS", "IN_REVIEW", "DONE", "CANCELLED"];
  subtype.initial = "TODO";
  subtype.terminal = ["DONE", "CANCELLED"];
  subtype.main_terminal = ["DONE"];
  subtype.side_terminal = ["CANCELLED"];
  subtype.fields = {
    reviewer: true,
    review_content: true,
    custom: [
      { key: "review_scope", label: "评审范围", label_en: "Review scope", type: "text" },
      { key: "risk_score", label: "风险分", label_en: "Risk score", type: "number" },
      {
        key: "observers",
        label: "旁听人",
        label_en: "Observers",
        type: "user",
        multiple: true,
      },
    ],
  };
  subtype.steps = {
    TODO: [
      { key: "START", name: "开始评审", name_en: "Start review", to: "IN_PROGRESS" },
      { key: "CANCEL", name: "取消", name_en: "Cancel", to: "CANCELLED" },
    ],
    IN_PROGRESS: [
      { key: "SUBMIT", name: "提交评审", name_en: "Submit review", to: "IN_REVIEW" },
      { key: "CANCEL", name: "取消", name_en: "Cancel", to: "CANCELLED" },
    ],
    IN_REVIEW: [
      {
        key: "APPROVE",
        name: "通过",
        name_en: "Approve",
        to: "DONE",
        mode: "direct",
        actors: ["assignee"],
        executors: { min: 1, max: 1 },
        note: "required",
      },
      { key: "CANCEL", name: "取消", name_en: "Cancel", to: "CANCELLED" },
    ],
    DONE: [],
    CANCELLED: [],
  };

  const saved = (
    await api.post<{ version: WorkflowConfigVersion }>(
      "/workflow-configs/e2e/versions",
      {
        content_text: `${JSON.stringify(raw, null, 2)}\n`,
        base_version_id: forked.version.id,
      },
    )
  ).data;
  return saved.version.id;
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
  const distIndex = path.join(repoRoot, "src/rdm/resources/web-next-dist/index.html");
  if (!fs.existsSync(distIndex)) {
    throw new Error(
      `SPA bundle missing at ${distIndex}. Run \`pnpm -C web-next build\` first ` +
        "(the `e2e` script does this automatically).",
    );
  }

  fs.rmSync(AUTH_DIR, { recursive: true, force: true });
  fs.mkdirSync(AUTH_DIR, { recursive: true });

  const dataDir = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "rdm-web-e2e-")), "data");
  const port = await freePort();
  const baseURL = `http://127.0.0.1:${port}`;
  const log = fs.createWriteStream(SERVER_LOG, { flags: "w" });
  const child = spawn(
    "uv",
    ["run", "rdm", "serve", "--data-dir", dataDir, "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: repoRoot,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        NO_PROXY: "127.0.0.1,localhost,::1",
        no_proxy: "127.0.0.1,localhost,::1",
        RDM_WEBHOOK_POLL_SECONDS: "0.5",
      },
    },
  );
  child.stdout?.pipe(log);
  child.stderr?.pipe(log);

  const teardown = async () => {
    await stopServer(child);
    log.end();
    fs.rmSync(path.dirname(dataDir), { recursive: true, force: true });
  };

  try {
    await waitForHealth(baseURL, child);
    await recoverOwner(baseURL);
    const ownerTokens = await oauthLogin(baseURL, "owner", OWNER_PASSWORD);
    const owner: Session = {
      id: "",
      name: "owner",
      password: OWNER_PASSWORD,
      ...ownerTokens,
    };
    const users = {} as E2EContext["users"];
    const ctx: E2EContext = { baseURL, projectKey: PROJECT_KEY, dataDir, owner, users };
    const api = new Api(ctx);

    // Resolve the owner's id from whoami.
    const whoami = await api.get<{ user: { id: string } }>("/whoami");
    owner.id = whoami.data.user.id;

    ctx.workflowConfigVersionId = await createE2EWorkflowConfig(api);
    await api.createProject(PROJECT_KEY, "Workflow E2E");

    for (const name of MEMBER_NAMES) {
      const created = await createUser(api, name);
      await setPassword(baseURL, created.password_reset_url, USER_PASSWORD);
      const tokens = await oauthLogin(baseURL, name, USER_PASSWORD);
      users[name as Exclude<UserName, "owner">] = {
        id: created.id,
        name,
        password: USER_PASSWORD,
        ...tokens,
      };
      await api.post(`/projects/${PROJECT_KEY}/members`, {
        user_id: created.id,
        roles: ["worker"],
      });
    }

    fs.writeFileSync(storageStateFor("owner"), JSON.stringify(storageState(baseURL, owner), null, 2));
    for (const name of MEMBER_NAMES) {
      fs.writeFileSync(
        storageStateFor(name as UserName),
        JSON.stringify(storageState(baseURL, users[name as Exclude<UserName, "owner">]), null, 2),
      );
    }
    fs.writeFileSync(
      path.join(AUTH_DIR, "context.json"),
      JSON.stringify(ctx, null, 2),
    );
    return teardown;
  } catch (error) {
    await teardown();
    throw error;
  }
}
