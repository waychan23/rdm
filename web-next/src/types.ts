/** Selected workflow config echoed by GET /projects/{key} (RDM-86). */
export interface ProjectWorkflowConfig {
  config_id: string;
  key: string;
  name: string;
  is_builtin: boolean;
  enabled: boolean;
  version_id: string;
  version: number;
  schema_version: number;
  revision: number;
  is_active: boolean;
  latest_version_id?: string | null;
  latest_version?: number | null;
  has_update?: boolean;
}

export interface Project {
  id: string;
  key: string;
  name: string;
  description_md?: string | null;
  owner_user_id?: string | null;
  status: string;
  created_at: string;
  roles?: string[];
  implicit?: boolean;
  membership_id?: string | null;
  unread_count?: number;
  /** Selected workflow config version (RDM-84); null = packaged default. */
  workflow_config_version_id?: string | null;
  /** Present on GET /projects/{key} (RDM-86). */
  workflow_config?: ProjectWorkflowConfig | null;
}

/** One immutable workflow config version (RDM-84). */
export interface WorkflowConfigVersion {
  id: string;
  config_id: string;
  version: number;
  schema_version: number;
  revision: number;
  content_hash: string;
  source_version_id?: string | null;
  is_active: boolean;
  created_at: string;
  created_by?: string | null;
  content_text?: string;
}

/** A selectable workflow config with its active version (RDM-84). */
export interface WorkflowConfig {
  id: string;
  key: string;
  name: string;
  is_builtin: boolean;
  enabled: boolean;
  current_version_id?: string | null;
  active_version?: WorkflowConfigVersion | null;
  version_count: number;
  created_at: string;
  updated_at?: string | null;
  versions?: WorkflowConfigVersion[];
}

/** Organization-level identity (human or agent), §17. */
export interface OrgUser {
  id: string;
  type: string;
  name: string;
  display_name?: string | null;
  description_md?: string | null;
  manager_user_id?: string | null;
  org_roles: string[];
  accept_kinds?: string[];
  email?: string | null;
  notify_webhook?: string | null;
  notify_webhook_format?: string;
  must_reset_password?: boolean;
  is_active: boolean;
  effective_active?: boolean;
  created_at: string;
}

/** A project membership row plus the human's agents (§17). */
export interface ProjectMemberRow extends OrgUser {
  membership_id: string;
  roles: string[];
  auto_added: boolean;
  agents?: Array<{ user: OrgUser; membership_id: string; auto_added: boolean }>;
}

export interface Assignee {
  id: string;
  name: string;
  display_name?: string | null;
  type: string;
}

export interface WorkItem {
  id: string;
  display_id: string;
  project_key: string;
  kind: string;
  task_type?: string | null;
  title: string;
  description_md?: string | null;
  status: string;
  priority: number;
  planned_start_date?: string | null;
  planned_end_date?: string | null;
  rank?: number;
  parent_id?: string | null;
  assignee?: Assignee | null;
  participants?: Assignee[];
  reviewer?: Assignee[];
  review_content_md?: string | null;
  custom_fields?: Record<string, unknown> | null;
  fields?: Record<string, unknown> | null;
  workflow_version?: number;
  workflow_def_id?: string | null;
  /** Sprint the item currently belongs to (list/board summaries, RDM-59). */
  sprint?: { id: string; name: string } | null;
  row_version: number;
  created_at: string;
  updated_at?: string | null;
  deleted_at?: string | null;
}

export interface WorkflowStepDef {
  key: string;
  name: string;
  to: string;
  mode: "direct" | "approval" | "task";
  actor_sources?: string[];
  executors: { min: number; max: number | null };
  note: "optional" | "required";
  gates: Record<string, unknown>;
  tasks: { type: string; title: string; complete_on: string } | null;
  candidates: Assignee[];
  auto_executors: Assignee[];
  can_start: boolean;
  can_execute: boolean;
  blocked_reasons: string[];
}

export interface StepExecutor {
  id: string;
  user: Assignee;
  status: "PENDING" | "DONE" | "CANCELLED";
  note_comment_id?: string | null;
  note_md?: string | null;
  task_id?: string | null;
  task?: { id: string; title: string; status: string } | null;
  completed_at?: string | null;
}

export interface ActiveStep {
  id: string;
  key: string;
  name: string;
  from: string;
  to: string;
  mode: "direct" | "approval" | "task";
  status: "PENDING" | "BLOCKED" | "COMPLETED" | "CANCELLED" | "REJECTED";
  row_version: number;
  required_count: number;
  config: Record<string, unknown>;
  gate_details?: Record<string, unknown> | null;
  created_at: string;
  executors: StepExecutor[];
  can_execute: boolean;
  can_reject: boolean;
  can_cancel: boolean;
  can_retry: boolean;
  can_reassign: boolean;
}

export interface WorkItemPermissions {
  can_edit?: boolean;
  can_assign?: boolean;
  can_start_steps?: boolean;
  can_execute?: boolean;
  can_delete?: boolean;
}

export interface WorkItemDetailMeta {
  allowed_transitions?: string[];
  children?: WorkItem[];
  parent?: WorkItem | null;
  /** Root-first ancestor chain (excluding the current item), for breadcrumbs. */
  ancestors?: WorkItem[];
  allowed_parent_kinds?: string[];
  allowed_child_kinds?: string[];
  available_steps?: WorkflowStepDef[];
  active_step?: ActiveStep | null;
  permissions?: WorkItemPermissions;
}

export interface HistoryChange {
  from?: unknown;
  to?: unknown;
  redacted?: boolean;
}

export interface HistoryEntry {
  id: number;
  seq: number;
  event_type: string;
  action: string;
  occurred_at: string;
  actor: { id: string; name?: string; display_name?: string | null; type?: string } | null;
  changes: Record<string, HistoryChange>;
  comment?: { id: string; excerpt?: string; reply_to_id?: string | null } | null;
  meta?: Record<string, unknown> | null;
}

export interface Attachment {
  id: string;
  owner_type: string;
  owner_id: string;
  filename: string;
  mime?: string | null;
  size_bytes: number;
  sha256: string;
  download_url: string;
  state?: "temp" | "active" | string;
  committed_at?: string | null;
  uploader: { id: string; name?: string; display_name?: string | null; type?: string };
  created_at: string;
}

export interface Artifact {
  id: string;
  owner_type: string;
  owner_id: string;
  kind: string;
  label: string;
  url: string;
  description_md?: string | null;
  created_at: string;
}

export interface Comment {
  id: string;
  work_item_id: string;
  body_md: string;
  reply_to_id?: string | null;
  author: { id: string; name?: string; display_name?: string | null; type?: string };
  attachments?: Attachment[];
  created_at: string;
  updated_at?: string | null;
  edited?: boolean;
}

export interface Sprint {
  id: string;
  project_id: string;
  name: string;
  goal_md?: string | null;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  manager_user_id?: string | null;
  created_at: string;
}

export interface SprintDetail extends Sprint {
  items: WorkItem[];
  status_counts: Record<string, number>;
}

export interface ReleaseStats {
  total: number;
  done: number;
  published: number;
  cancelled: number;
  percent: number;
}

export interface Release {
  id: string;
  project_id: string;
  name: string;
  description_md?: string | null;
  status: string;
  target_date?: string | null;
  released_at?: string | null;
  manager_user_id?: string | null;
  stats: ReleaseStats;
  created_at: string;
  updated_at?: string | null;
}

export interface ReleaseBlockingItem {
  id: string;
  display_id: string;
  title: string;
  status: string;
}

export interface ReleaseDetail extends Release {
  items: WorkItem[];
  status_counts: Record<string, number>;
  readiness: {
    can_publish: boolean;
    blocking: ReleaseBlockingItem[];
  };
}

export interface Workspace {
  id: string;
  project_id: string;
  name: string;
  kind: string;
  url: string;
  description_md?: string | null;
  default_branch?: string | null;
  created_at: string;
}

export interface MailMessage {
  delivery_id: string;
  message_id: string;
  thread_id?: string;
  project?: { id: string; key: string; name: string };
  from: { id: string; name?: string; display_name?: string | null; type?: string };
  mailbox_owner?: { id: string; name?: string; display_name?: string | null; type?: string };
  subject: string;
  body_md: string;
  recipient_type: string;
  recipients?: Array<{
    id: string;
    name?: string;
    display_name?: string | null;
    type?: string;
    recipient_type?: string;
  }>;
  refs: string[];
  reply_to_id?: string | null;
  read_at?: string | null;
  archived_at?: string | null;
  created_at: string;
}

export interface MailGroup {
  id: string;
  name: string;
  kind: string;
  members: Array<{ id: string; name: string; display_name?: string | null; type: string }>;
  created_at: string;
}

export interface Mailbox {
  messages: MailMessage[];
  next_cursor: string | null;
  unread_count: number;
}

export type EmailSecurity = "none" | "starttls" | "ssl";

export interface EmailSettings {
  id: string;
  enabled: boolean;
  smtp_host: string | null;
  smtp_port: number;
  smtp_security: EmailSecurity;
  smtp_username: string | null;
  from_address: string | null;
  from_name: string | null;
  has_password: boolean;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface CustomFieldDef {
  key: string;
  label: string;
  type: "text" | "number" | "user";
  multiple: boolean;
}

export interface WorkflowFields {
  reviewer: boolean;
  review_content: boolean;
  custom: CustomFieldDef[];
}

export interface WorkflowStep {
  key: string;
  name: string;
  to: string;
  mode: "direct" | "approval" | "task";
  actors: string[];
  executors: { min: number; max: number | null };
  note: "optional" | "required";
  gates: Record<string, unknown>;
  tasks: { type: string; title: string; complete_on: string } | null;
}

export interface WorkflowKind {
  label?: string;
  states: string[];
  initial: string;
  terminal: string[];
  transitions: Record<string, string[]>;
  steps?: Record<string, WorkflowStep[]>;
  gates: Record<string, unknown>;
  fields?: WorkflowFields;
  subtypes?: Record<string, WorkflowKind>;
}

export interface WorkflowDto {
  version: number;
  revision: number;
  task_types: { value: string; label: string }[];
  kinds: Record<string, WorkflowKind>;
}

export interface Token {
  id: string;
  user_id: string;
  act_as_user_id?: string | null;
  label?: string | null;
  kind: string;
  expires_at?: string | null;
  last_used_at?: string | null;
  revoked_at?: string | null;
  created_at: string;
  is_valid: boolean;
  /** Present only in the create response. */
  token?: string;
}

export interface Whoami {
  user: OrgUser;
  identity: { id: string; name: string; display_name?: string | null; type: string; act_as: boolean };
  org_roles: string[];
  agents: OrgUser[];
  projects: Project[];
  default_project: Project | null;
  unread_count: number;
  notification_unread_count: number;
  my_open_items: number;
}

export interface Notification {
  id: string;
  recipient_user_id: string;
  type: "assignment" | "step" | "comment" | "mention" | "system" | string;
  title: string;
  body?: string | null;
  project_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  entity_ref?: string | null;
  url?: string | null;
  read_at?: string | null;
  created_at: string;
}

export interface TodoStepEntry {
  step: {
    id: string;
    key: string;
    name: string;
    mode: string;
    status: string;
  };
  executor_user_id: string;
  project_key: string;
  item: WorkItem;
}

export interface TodoBundle {
  assigned: WorkItem[];
  pending_steps: TodoStepEntry[];
  approvals: TodoStepEntry[];
  overdue: WorkItem[];
  mentions: Notification[];
}

export interface SearchHit {
  entity_type: "work_item" | "comment" | "message" | "artifact" | string;
  entity_id: string;
  project_key: string;
  ref: string;
  title: string;
  snippet: string;
  url: string;
}
