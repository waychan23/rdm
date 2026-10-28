export interface Project {
  id: string;
  key: string;
  name: string;
  description_md?: string | null;
  owner_member_id?: string | null;
  status: string;
  created_at: string;
}

export interface Member {
  id: string;
  project_id?: string;
  name: string;
  type: string;
  description_md?: string | null;
  manager_member_id?: string | null;
  roles: string[];
  accept_kinds?: string[];
  email?: string | null;
  notify_webhook?: string | null;
  notify_webhook_format?: string;
  is_active: boolean;
  created_at: string;
}

export interface Assignee {
  id: string;
  name: string;
  type: string;
}

export interface WorkItem {
  id: string;
  display_id: string;
  project_key: string;
  kind: string;
  title: string;
  description_md?: string | null;
  status: string;
  priority: number;
  rank?: number;
  parent_id?: string | null;
  assignee?: Assignee | null;
  fields?: Record<string, unknown> | null;
  row_version: number;
  created_at: string;
  updated_at?: string | null;
  deleted_at?: string | null;
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
  uploader: { id: string; name?: string; type?: string };
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
  author: { id: string; name?: string; type?: string };
  attachments?: Attachment[];
  created_at: string;
}

export interface Sprint {
  id: string;
  project_id: string;
  name: string;
  goal_md?: string | null;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  manager_member_id?: string | null;
  created_at: string;
}

export interface SprintDetail extends Sprint {
  items: WorkItem[];
  status_counts: Record<string, number>;
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
  from: { id: string; name?: string; type?: string };
  subject: string;
  body_md: string;
  recipient_type: string;
  refs: string[];
  reply_to_id?: string | null;
  read_at?: string | null;
  created_at: string;
}

export interface Mailbox {
  messages: MailMessage[];
  next_cursor: string | null;
  unread_count: number;
}

export interface WorkflowKind {
  states: string[];
  initial: string;
  terminal: string[];
  transitions: Record<string, string[]>;
  gates: Record<string, unknown>;
}

export interface WorkflowDto {
  version: number;
  kinds: Record<string, WorkflowKind>;
}

export interface Token {
  id: string;
  member_id: string;
  label?: string | null;
  last_used_at?: string | null;
  revoked_at?: string | null;
  created_at: string;
  is_valid: boolean;
}

export interface Whoami {
  member: Member;
  project: Project | null;
  roles: string[];
  unread_count: number;
  my_open_items: number;
}
