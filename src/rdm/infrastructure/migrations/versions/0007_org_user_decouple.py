# ruff: noqa: E501
"""M5: identity decoupling — organization / users / project_member (§17).

The old model attached every identity to a project (``project_member`` was
the user). M5 splits it into ``organization`` → ``users`` (human/agent) and
``project_member`` (project ↔ user relationship). Because the shapes are not
compatible, this migration **only accepts an empty database**:

* if any legacy business row exists it aborts with instructions (back up,
  delete ``rdm.db``, re-run ``rdm db upgrade``);
* otherwise it drops the 23 legacy tables and creates the 27 new ones.

The DDL below is a frozen snapshot generated from the ORM metadata at the
time of writing, so replaying the chain always yields the same schema.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect, text

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# Legacy tables present at 0006 (alembic_version excluded).
_OLD_TABLES: Sequence[str] = [
    "artifact",
    "attachment",
    "comment",
    "event",
    "mailbox",
    "mailbox_member",
    "message",
    "message_delivery",
    "message_ref",
    "oauth_authorization_code",
    "oauth_client",
    "oauth_consent_request",
    "project",
    "project_member",
    "member_token",
    "sprint",
    "sprint_item",
    "webhook_outbox",
    "work_item",
    "work_item_issue",
    "work_item_story",
    "work_item_task",
    "workspace",
]

# New tables created by this migration (§17).
_NEW_TABLES: Sequence[str] = [
    "artifact",
    "attachment",
    "comment",
    "event",
    "mailbox",
    "mailbox_member",
    "message",
    "message_delivery",
    "message_ref",
    "oauth_authorization_code",
    "oauth_client",
    "oauth_consent_request",
    "oauth_login_ticket",
    "organization",
    "password_set_token",
    "project",
    "project_member",
    "sprint",
    "sprint_item",
    "user_token",
    "users",
    "webhook_outbox",
    "work_item",
    "work_item_issue",
    "work_item_story",
    "work_item_task",
    "workspace",
]

_DDL: Sequence[str] = [
    """CREATE TABLE oauth_authorization_code (
	id VARCHAR(32) NOT NULL, 
	code_hash VARCHAR(64) NOT NULL, 
	client_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	act_as_user_id VARCHAR(32), 
	remember BOOLEAN DEFAULT '0' NOT NULL, 
	scopes JSON NOT NULL, 
	code_challenge VARCHAR(128) NOT NULL, 
	redirect_uri TEXT NOT NULL, 
	redirect_uri_explicit BOOLEAN NOT NULL, 
	resource VARCHAR(500), 
	expires_at DATETIME NOT NULL, 
	consumed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_oauth_authorization_code PRIMARY KEY (id), 
	CONSTRAINT uq_oauth_authorization_code_code_hash UNIQUE (code_hash)
)""",
    """CREATE TABLE oauth_client (
	client_id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	client_info JSON NOT NULL, 
	redirect_uris JSON NOT NULL, 
	is_first_party BOOLEAN DEFAULT '0' NOT NULL, 
	created_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	CONSTRAINT pk_oauth_client PRIMARY KEY (client_id)
)""",
    """CREATE TABLE oauth_consent_request (
	id VARCHAR(32) NOT NULL, 
	client_id VARCHAR(36) NOT NULL, 
	consent_key_hash VARCHAR(64) NOT NULL, 
	authenticating_user_id VARCHAR(32) NOT NULL, 
	selectable_user_ids JSON NOT NULL, 
	remember BOOLEAN DEFAULT '0' NOT NULL, 
	state VARCHAR(255), 
	scopes JSON NOT NULL, 
	code_challenge VARCHAR(128) NOT NULL, 
	redirect_uri TEXT NOT NULL, 
	redirect_uri_explicit BOOLEAN NOT NULL, 
	resource VARCHAR(500), 
	expires_at DATETIME NOT NULL, 
	decided_at DATETIME, 
	consumed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_oauth_consent_request PRIMARY KEY (id), 
	CONSTRAINT uq_oauth_consent_request_consent_key_hash UNIQUE (consent_key_hash)
)""",
    """CREATE TABLE oauth_login_ticket (
	id VARCHAR(32) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	key_hash VARCHAR(64) NOT NULL, 
	client_id VARCHAR(36) NOT NULL, 
	code_challenge VARCHAR(128) NOT NULL, 
	redirect_uri TEXT NOT NULL, 
	redirect_uri_explicit BOOLEAN NOT NULL, 
	scopes JSON NOT NULL, 
	state VARCHAR(255), 
	resource VARCHAR(500), 
	expires_at DATETIME NOT NULL, 
	consumed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_oauth_login_ticket PRIMARY KEY (id), 
	CONSTRAINT uq_oauth_login_ticket_key_hash UNIQUE (key_hash)
)""",
    """CREATE INDEX ix_oauth_login_ticket_hash ON oauth_login_ticket (key_hash)""",
    """CREATE TABLE organization (
	id VARCHAR(32) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	event_seq INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME, 
	CONSTRAINT pk_organization PRIMARY KEY (id)
)""",
    """CREATE TABLE project (
	id VARCHAR(32) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	"key" VARCHAR(12) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	owner_user_id VARCHAR(32), 
	description_md TEXT, 
	status VARCHAR(20) NOT NULL, 
	item_seq INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_project PRIMARY KEY (id), 
	CONSTRAINT fk_project_org_id_organization FOREIGN KEY(org_id) REFERENCES organization (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE UNIQUE INDEX ux_project_org_key_lower ON project (org_id, lower(key)) WHERE deleted_at IS NULL""",
    """CREATE TABLE users (
	id VARCHAR(32) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	type VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description_md TEXT, 
	manager_user_id VARCHAR(32), 
	org_roles JSON NOT NULL, 
	accept_kinds JSON NOT NULL, 
	email VARCHAR(200), 
	notify_webhook VARCHAR(500), 
	notify_webhook_format VARCHAR(10) DEFAULT 'generic' NOT NULL, 
	password_hash VARCHAR(255), 
	must_reset_password BOOLEAN DEFAULT '0' NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT ck_users_agent_requires_manager CHECK (type = 'human' OR manager_user_id IS NOT NULL), 
	CONSTRAINT fk_users_org_id_organization FOREIGN KEY(org_id) REFERENCES organization (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_users_manager_user_id_users FOREIGN KEY(manager_user_id) REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE INDEX ix_users_manager ON users (manager_user_id)""",
    """CREATE INDEX ix_users_org_type ON users (org_id, type)""",
    """CREATE UNIQUE INDEX ux_users_org_name_lower ON users (org_id, lower(name)) WHERE deleted_at IS NULL""",
    """CREATE TABLE artifact (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	owner_type VARCHAR(20) NOT NULL, 
	owner_id VARCHAR(32) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	url VARCHAR(1000) NOT NULL, 
	description_md TEXT, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_artifact PRIMARY KEY (id), 
	CONSTRAINT fk_artifact_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE attachment (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	owner_type VARCHAR(20) NOT NULL, 
	owner_id VARCHAR(32) NOT NULL, 
	uploader_user_id VARCHAR(32) NOT NULL, 
	filename VARCHAR(300) NOT NULL, 
	mime VARCHAR(200), 
	size_bytes BIGINT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	rel_path VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_attachment PRIMARY KEY (id), 
	CONSTRAINT fk_attachment_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE event (
	id INTEGER NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32), 
	seq INTEGER NOT NULL, 
	aggregate_type VARCHAR(30) NOT NULL, 
	aggregate_id VARCHAR(32) NOT NULL, 
	aggregate_version INTEGER NOT NULL, 
	event_type VARCHAR(50) NOT NULL, 
	actor_user_id VARCHAR(32), 
	payload JSON NOT NULL, 
	occurred_at DATETIME NOT NULL, 
	CONSTRAINT pk_event PRIMARY KEY (id), 
	CONSTRAINT ux_event_org_seq UNIQUE (org_id, seq), 
	CONSTRAINT fk_event_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE INDEX ix_event_org_aggregate ON event (org_id, aggregate_type, aggregate_id, id)""",
    """CREATE TABLE mailbox (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	kind VARCHAR(10) NOT NULL, 
	name VARCHAR(100), 
	owner_user_id VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_mailbox PRIMARY KEY (id), 
	CONSTRAINT fk_mailbox_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE UNIQUE INDEX ux_mailbox_indiv_owner ON mailbox (project_id, owner_user_id) WHERE kind = 'indiv' AND deleted_at IS NULL""",
    """CREATE TABLE message (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	from_user_id VARCHAR(32) NOT NULL, 
	subject VARCHAR(300) NOT NULL, 
	body_md TEXT NOT NULL, 
	reply_to_id VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_message PRIMARY KEY (id), 
	CONSTRAINT fk_message_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE password_set_token (
	id VARCHAR(32) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	consumed_at DATETIME, 
	created_by VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_password_set_token PRIMARY KEY (id), 
	CONSTRAINT ck_password_set_token_ck_password_set_token_kind CHECK (kind in ('bootstrap', 'reset', 'must_reset')), 
	CONSTRAINT fk_password_set_token_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT uq_password_set_token_token_hash UNIQUE (token_hash)
)""",
    """CREATE INDEX ix_password_set_token_user_kind ON password_set_token (user_id, kind)""",
    """CREATE TABLE project_member (
	id VARCHAR(32) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	roles JSON NOT NULL, 
	auto_added BOOLEAN DEFAULT '0' NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_project_member PRIMARY KEY (id), 
	CONSTRAINT fk_project_member_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_project_member_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE INDEX ix_project_member_org ON project_member (org_id)""",
    """CREATE INDEX ix_project_member_user ON project_member (user_id)""",
    """CREATE UNIQUE INDEX ux_project_member_project_user ON project_member (project_id, user_id) WHERE deleted_at IS NULL""",
    """CREATE TABLE sprint (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	goal_md TEXT, 
	status VARCHAR(10) NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	manager_user_id VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_sprint PRIMARY KEY (id), 
	CONSTRAINT fk_sprint_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE UNIQUE INDEX ux_sprint_one_active_per_project ON sprint (project_id) WHERE status = 'ACTIVE' AND deleted_at IS NULL""",
    """CREATE TABLE user_token (
	id VARCHAR(32) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	act_as_user_id VARCHAR(32), 
	token_hash VARCHAR(64) NOT NULL, 
	label VARCHAR(100), 
	kind VARCHAR(16) DEFAULT 'pat' NOT NULL, 
	expires_at DATETIME, 
	absolute_expires_at DATETIME, 
	remember BOOLEAN DEFAULT '0' NOT NULL, 
	client_id VARCHAR(36), 
	scopes JSON DEFAULT '[]' NOT NULL, 
	family_id VARCHAR(32), 
	consumed_at DATETIME, 
	last_used_at DATETIME, 
	revoked_at DATETIME, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_user_token PRIMARY KEY (id), 
	CONSTRAINT ck_user_token_ck_user_token_kind CHECK (kind in ('pat', 'oauth_access', 'oauth_refresh')), 
	CONSTRAINT fk_user_token_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_user_token_act_as_user_id_users FOREIGN KEY(act_as_user_id) REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT uq_user_token_token_hash UNIQUE (token_hash)
)""",
    """CREATE INDEX ix_user_token_act_as ON user_token (act_as_user_id)""",
    """CREATE INDEX ix_user_token_family ON user_token (family_id)""",
    """CREATE INDEX ix_user_token_user_kind ON user_token (user_id, kind)""",
    """CREATE TABLE work_item (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	display_no INTEGER NOT NULL, 
	kind VARCHAR(10) NOT NULL, 
	parent_id VARCHAR(32), 
	title VARCHAR(300) NOT NULL, 
	description_md TEXT, 
	status VARCHAR(20) NOT NULL, 
	priority INTEGER NOT NULL, 
	rank INTEGER NOT NULL, 
	assignee_user_id VARCHAR(32), 
	row_version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_work_item PRIMARY KEY (id), 
	CONSTRAINT fk_work_item_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_work_item_parent_id_work_item FOREIGN KEY(parent_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE INDEX ix_work_item_project_assignee_status ON work_item (project_id, assignee_user_id, status)""",
    """CREATE INDEX ix_work_item_project_kind_status ON work_item (project_id, kind, status)""",
    """CREATE INDEX ix_work_item_project_parent ON work_item (project_id, parent_id)""",
    """CREATE UNIQUE INDEX ux_work_item_project_display_no ON work_item (project_id, display_no) WHERE deleted_at IS NULL""",
    """CREATE TABLE workspace (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	url VARCHAR(1000) NOT NULL, 
	description_md TEXT, 
	default_branch VARCHAR(200), 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_workspace PRIMARY KEY (id), 
	CONSTRAINT fk_workspace_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE comment (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	work_item_id VARCHAR(32) NOT NULL, 
	author_user_id VARCHAR(32) NOT NULL, 
	body_md TEXT NOT NULL, 
	reply_to_id VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	created_by VARCHAR, 
	updated_at DATETIME, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_comment PRIMARY KEY (id), 
	CONSTRAINT fk_comment_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_comment_work_item_id_work_item FOREIGN KEY(work_item_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE mailbox_member (
	id VARCHAR(32) NOT NULL, 
	mailbox_id VARCHAR(32) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	added_by VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_mailbox_member PRIMARY KEY (id), 
	CONSTRAINT fk_mailbox_member_mailbox_id_mailbox FOREIGN KEY(mailbox_id) REFERENCES mailbox (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE UNIQUE INDEX ux_mailbox_member ON mailbox_member (mailbox_id, user_id) WHERE deleted_at IS NULL""",
    """CREATE TABLE message_delivery (
	id VARCHAR(32) NOT NULL, 
	message_id VARCHAR(32) NOT NULL, 
	mailbox_id VARCHAR(32) NOT NULL, 
	recipient_user_id VARCHAR(32) NOT NULL, 
	recipient_type VARCHAR(5) NOT NULL, 
	read_at DATETIME, 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_message_delivery PRIMARY KEY (id), 
	CONSTRAINT fk_message_delivery_message_id_message FOREIGN KEY(message_id) REFERENCES message (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_message_delivery_mailbox_id_mailbox FOREIGN KEY(mailbox_id) REFERENCES mailbox (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE INDEX ix_delivery_message ON message_delivery (message_id)""",
    """CREATE INDEX ix_delivery_recipient_read ON message_delivery (recipient_user_id, read_at)""",
    """CREATE TABLE message_ref (
	id VARCHAR(32) NOT NULL, 
	message_id VARCHAR(32) NOT NULL, 
	work_item_id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_message_ref PRIMARY KEY (id), 
	CONSTRAINT fk_message_ref_message_id_message FOREIGN KEY(message_id) REFERENCES message (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_message_ref_work_item_id_work_item FOREIGN KEY(work_item_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE sprint_item (
	id VARCHAR(32) NOT NULL, 
	sprint_id VARCHAR(32) NOT NULL, 
	work_item_id VARCHAR(32) NOT NULL, 
	added_by VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	deleted_by VARCHAR, 
	CONSTRAINT pk_sprint_item PRIMARY KEY (id), 
	CONSTRAINT fk_sprint_item_sprint_id_sprint FOREIGN KEY(sprint_id) REFERENCES sprint (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_sprint_item_work_item_id_work_item FOREIGN KEY(work_item_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE UNIQUE INDEX ux_sprint_item_one_sprint ON sprint_item (work_item_id) WHERE deleted_at IS NULL""",
    """CREATE TABLE webhook_outbox (
	id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32) NOT NULL, 
	event_id BIGINT NOT NULL, 
	target_url VARCHAR(1000) NOT NULL, 
	format VARCHAR(10) NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt_at DATETIME, 
	last_error VARCHAR(1000), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME, 
	CONSTRAINT pk_webhook_outbox PRIMARY KEY (id), 
	CONSTRAINT fk_webhook_outbox_project_id_project FOREIGN KEY(project_id) REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_webhook_outbox_event_id_event FOREIGN KEY(event_id) REFERENCES event (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE work_item_issue (
	work_item_id VARCHAR(32) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	environment VARCHAR(300), 
	repro_steps_md TEXT, 
	expected_behavior_md TEXT, 
	actual_behavior_md TEXT, 
	source_story_id VARCHAR(32), 
	CONSTRAINT pk_work_item_issue PRIMARY KEY (work_item_id), 
	CONSTRAINT fk_work_item_issue_work_item_id_work_item FOREIGN KEY(work_item_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE work_item_story (
	work_item_id VARCHAR(32) NOT NULL, 
	acceptance_criteria_md TEXT, 
	CONSTRAINT pk_work_item_story PRIMARY KEY (work_item_id), 
	CONSTRAINT fk_work_item_story_work_item_id_work_item FOREIGN KEY(work_item_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE work_item_task (
	work_item_id VARCHAR(32) NOT NULL, 
	task_type VARCHAR(20) NOT NULL, 
	est_work_hours NUMERIC(6, 1), 
	actual_work_hours NUMERIC(6, 1), 
	code_branch VARCHAR(200), 
	CONSTRAINT pk_work_item_task PRIMARY KEY (work_item_id), 
	CONSTRAINT fk_work_item_task_work_item_id_work_item FOREIGN KEY(work_item_id) REFERENCES work_item (id) DEFERRABLE INITIALLY DEFERRED
)""",
]


def _row_counts(bind, existing: set[str]) -> dict[str, int]:
    # Only query tables the inspector confirmed: PostgreSQL aborts the whole
    # transaction on an undefined-table error, unlike SQLite.
    return {
        table: int(bind.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
        for table in _OLD_TABLES
        if table in existing
    }


def _ddl_for(statement: str, dialect: str) -> str:
    """Adapt the frozen SQLite-dialect DDL snapshot for PostgreSQL (§17.114)."""
    if dialect != "postgresql":
        return statement
    sql = statement
    if sql.lstrip().startswith("CREATE TABLE event"):
        sql = sql.replace(
            "id INTEGER NOT NULL,",
            "id BIGINT GENERATED BY DEFAULT AS IDENTITY NOT NULL,",
            1,
        )
    sql = sql.replace("DATETIME", "TIMESTAMP WITH TIME ZONE")
    sql = sql.replace("BOOLEAN DEFAULT '0'", "BOOLEAN DEFAULT FALSE")
    return sql


def _drop(bind, table: str) -> None:
    if bind.dialect.name == "postgresql":
        # Alphabetical drops would fail on FK-referenced tables without CASCADE.
        op.execute(f'DROP TABLE "{table}" CASCADE')
    else:
        op.execute(f'DROP TABLE "{table}"')


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())

    counts = {k: v for k, v in _row_counts(bind, existing).items() if v}
    if counts:
        raise RuntimeError(
            "M5 身份模型与旧库不兼容，且不提供数据迁移。"
            "请先停止服务并备份：cp rdm.db rdm.db.bak；"
            "然后删除 rdm.db、rdm.db-wal、rdm.db-shm，再执行 rdm db upgrade。"
            f"（检测到非空旧表：{', '.join(sorted(counts))}）"
        )

    drop_names = set(_OLD_TABLES) | set(_NEW_TABLES)
    for table in sorted(drop_names):
        if table in existing:
            _drop(bind, table)

    for statement in _DDL:
        op.execute(_ddl_for(statement, bind.dialect.name))


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table in reversed(_NEW_TABLES):
        if table in existing:
            _drop(bind, table)
