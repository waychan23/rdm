export interface Project {
  id: string;
  key: string;
  name: string;
  description_md?: string | null;
  status: string;
  created_at: string;
}

export interface Member {
  id: string;
  name: string;
  type: string;
  roles: string[];
  manager_member_id?: string | null;
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
  assignee?: Assignee | null;
  fields?: Record<string, unknown> | null;
  row_version: number;
  created_at: string;
  updated_at?: string | null;
  deleted_at?: string | null;
}

export interface Comment {
  id: string;
  work_item_id: string;
  body_md: string;
  reply_to_id?: string | null;
  author: { id: string; name?: string; type?: string };
  created_at: string;
}
