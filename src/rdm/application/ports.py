"""Ports (Protocols) for repositories, event store, clock and UoW.

Infrastructure implements these; wiring happens only in app assembly.
M0 defines ports needed by project/member/auth/work-item foundation;
M1 extends with sprint/mailbox/comment repositories; M2 adds collaboration
(attachment/artifact/workspace), outbox and the on-disk file store.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from rdm.domain.entities import (
    Artifact,
    Attachment,
    Comment,
    Mailbox,
    MailboxMember,
    Message,
    MessageDelivery,
    MessageRef,
    Notification,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthLoginTicket,
    Organization,
    OutboxRow,
    PasswordTicket,
    Project,
    ProjectMember,
    Sprint,
    SprintItem,
    User,
    UserToken,
    WorkItem,
    Workspace,
)
from rdm.domain.events import EventRecord, EventType

# Type aliases: inside the Protocol bodies below, a method named `list`
# shadows the builtin, so `list[...]` annotations must use the alias.
ProjectList = list[Project]
UserList = list[User]
MembershipList = list[ProjectMember]
TokenList = list[UserToken]
WorkItemList = list[WorkItem]
SprintList = list[Sprint]
SprintItemList = list[SprintItem]
CommentList = list[Comment]
MailboxList = list[Mailbox]
MailboxMemberList = list[MailboxMember]
MessageList = list[Message]
DeliveryList = list[MessageDelivery]
MessageRefList = list[MessageRef]
NotificationList = list[Notification]
AttachmentList = list[Attachment]
ArtifactList = list[Artifact]
WorkspaceList = list[Workspace]


@dataclass(frozen=True)
class SavedFile:
    rel_path: str
    size_bytes: int
    sha256: str


class FileStore(Protocol):
    async def save(
        self, project_id: str, filename: str, stream: Any, *, max_bytes: int
    ) -> SavedFile: ...

    def abspath(self, rel_path: str) -> Path: ...

    def exists(self, rel_path: str) -> bool: ...

    def iter_attachment_relpaths(
        self, project_id: str | None = None
    ) -> Iterable[tuple[str, str]]: ...


class Clock(Protocol):
    def now(self) -> dt.datetime: ...


class ProjectRepository(Protocol):
    async def get(self, project_id: str) -> Project | None: ...

    async def get_by_key(self, key: str, *, include_deleted: bool = False) -> Project | None: ...

    async def add(self, project: Project) -> None: ...

    async def update(self, project: Project) -> None: ...

    async def list_all(self, *, include_deleted: bool = False) -> ProjectList: ...


class OrganizationRepository(Protocol):
    async def get(self, org_id: str) -> Organization | None: ...

    async def add(self, org: Organization) -> None: ...

    async def update(self, org: Organization) -> None: ...


class UserRepository(Protocol):
    async def get(self, user_id: str, *, include_deleted: bool = False) -> User | None: ...

    async def get_by_name(
        self, org_id: str, name: str, *, include_deleted: bool = False
    ) -> User | None: ...

    async def list_by_org(
        self, org_id: str, *, type: str | None = None, include_deleted: bool = False
    ) -> UserList: ...

    async def list_agents_of(self, manager_user_id: str) -> UserList: ...

    async def list_org_owners(self, org_id: str) -> UserList: ...

    async def add(self, user: User) -> None: ...

    async def update(self, user: User) -> None: ...


class MembershipRepository(Protocol):
    async def get(
        self, project_id: str, user_id: str, *, include_deleted: bool = False
    ) -> ProjectMember | None: ...

    async def list_by_project(
        self, project_id: str, *, include_deleted: bool = False
    ) -> MembershipList: ...

    async def list_by_user(
        self, user_id: str, *, include_deleted: bool = False
    ) -> MembershipList: ...

    async def add(self, membership: ProjectMember) -> None: ...

    async def revive(self, membership: ProjectMember) -> None: ...

    async def update(self, membership: ProjectMember) -> None: ...

    async def soft_delete(self, membership_id: str, actor_id: str, when: dt.datetime) -> bool: ...


class TokenRepository(Protocol):
    async def add(self, token: UserToken) -> None: ...

    async def get(self, token_id: str) -> UserToken | None: ...

    async def get_by_hash(self, token_hash: str) -> UserToken | None: ...

    async def list_by_user(self, user_id: str, *, kind: str | None = None) -> TokenList: ...

    async def revoke(self, token_id: str) -> bool: ...

    async def revoke_by_user_kind(self, user_id: str, kind: str) -> int: ...

    async def revoke_all_for_user(self, user_id: str, *, kinds: list[str] | None = None) -> int: ...

    async def revoke_all_for_act_as(
        self, act_as_user_id: str, *, kinds: list[str] | None = None
    ) -> int: ...

    async def revoke_family(self, family_id: str) -> int: ...

    async def count_valid_pat(self, user_id: str) -> int: ...

    async def touch_last_used(self, token_id: str, when: dt.datetime) -> None: ...


class PasswordTicketRepository(Protocol):
    async def add(self, ticket: PasswordTicket) -> None: ...

    async def get_by_hash(self, token_hash: str) -> PasswordTicket | None: ...

    async def consume(self, ticket_id: str, when: dt.datetime) -> None: ...

    async def invalidate_kind(self, user_id: str, kind: str, when: dt.datetime) -> int: ...


class OAuthClientRepository(Protocol):
    async def upsert(self, client: OAuthClient) -> None: ...

    async def get(self, client_id: str) -> OAuthClient | None: ...


class AuthorizationCodeRepository(Protocol):
    async def add(self, code: OAuthAuthorizationCode) -> None: ...

    async def get_by_hash(self, code_hash: str) -> OAuthAuthorizationCode | None: ...

    async def mark_consumed(self, code_id: str, when: dt.datetime) -> None: ...


class ConsentRepository(Protocol):
    async def add(self, consent: OAuthConsent) -> None: ...

    async def get(self, consent_id: str) -> OAuthConsent | None: ...

    async def mark_decided(self, consent_id: str, when: dt.datetime) -> None: ...


class LoginTicketRepository(Protocol):
    async def add(self, ticket: OAuthLoginTicket) -> None: ...

    async def get_by_hash(self, key_hash: str) -> OAuthLoginTicket | None: ...

    async def consume(self, ticket_id: str, when: dt.datetime) -> None: ...


class WorkItemRepository(Protocol):
    async def add(self, item: WorkItem) -> None: ...

    async def get(
        self, item_id: str, *, expand: bool = True, include_deleted: bool = False
    ) -> WorkItem | None: ...

    async def list(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        kinds: Sequence[str] | None = None,
        status: str | None = None,
        assignee_user_id: str | None = None,
        parent_id: str | None = None,
        q: str | None = None,
        exclude_statuses: Sequence[str] | None = None,
        backlog_only: bool = False,
        expand: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkItemList: ...

    async def count(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        kinds: Sequence[str] | None = None,
        status: str | None = None,
        assignee_user_id: str | None = None,
        parent_id: str | None = None,
        q: str | None = None,
        exclude_statuses: Sequence[str] | None = None,
        backlog_only: bool = False,
        include_deleted: bool = False,
    ) -> int: ...

    async def get_by_display_no(
        self, project_id: str, display_no: int, *, include_deleted: bool = False
    ) -> WorkItem | None: ...

    async def list_by_ids(
        self, project_id: str, item_ids: Sequence[str], *, include_deleted: bool = False
    ) -> WorkItemList: ...

    async def list_children(
        self, parent_id: str, *, include_deleted: bool = False
    ) -> WorkItemList: ...

    async def restore(self, ids: Sequence[str]) -> int: ...

    async def save(self, item: WorkItem) -> None:
        """Persist optimistic-lock update; 0 rows -> ConflictVersion."""
        ...

    async def claim(self, item_id: str, user_id: str, actor_id: str) -> bool:
        """Atomic claim; False when already assigned (caller raises ALREADY_ASSIGNED)."""
        ...

    async def soft_delete(
        self, item_id: str, actor_id: str, *, cascade_ids: Sequence[str] | None = None
    ) -> Sequence[str]: ...


class SprintRepository(Protocol):
    async def add(self, sprint: Sprint) -> None: ...

    async def get(self, sprint_id: str, *, include_deleted: bool = False) -> Sprint | None: ...

    async def list(
        self,
        project_id: str,
        *,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> SprintList: ...

    async def active_for_project(self, project_id: str) -> Sprint | None: ...

    async def save_status(self, sprint: Sprint) -> None: ...


class SprintItemRepository(Protocol):
    async def bulk_add(self, items: Sequence[SprintItem]) -> None: ...

    async def remove(self, sprint_id: str, work_item_id: str, actor_id: str) -> bool: ...

    async def list_for_sprint(self, sprint_id: str) -> SprintItemList: ...

    async def active_link_for_item(self, work_item_id: str) -> SprintItem | None: ...


class CommentRepository(Protocol):
    async def add(self, comment: Comment) -> None: ...

    async def get(self, comment_id: str) -> Comment | None: ...

    async def list_for_item(
        self, work_item_id: str, *, limit: int = 100, offset: int = 0
    ) -> CommentList: ...

    async def soft_delete(self, comment_id: str, actor_id: str, when: dt.datetime) -> bool: ...


class AttachmentRepository(Protocol):
    async def add(self, attachment: Attachment) -> None: ...

    async def get(
        self, attachment_id: str, *, include_deleted: bool = False
    ) -> Attachment | None: ...

    async def list_for_owner(
        self,
        project_id: str,
        owner_type: str,
        owner_id: str,
        *,
        include_deleted: bool = False,
    ) -> AttachmentList: ...

    async def list_for_owners(
        self, project_id: str, owner_type: str, owner_ids: Sequence[str]
    ) -> AttachmentList: ...

    async def list_by_ids(
        self,
        project_id: str,
        attachment_ids: Sequence[str],
        *,
        active_only: bool = False,
    ) -> AttachmentList: ...

    async def commit_temp(
        self, project_id: str, attachment_ids: Sequence[str], when: dt.datetime
    ) -> int: ...

    async def list_temp_older_than(
        self, cutoff: dt.datetime, *, limit: int = 100
    ) -> AttachmentList: ...

    async def soft_delete(self, attachment_id: str, actor_id: str, when: dt.datetime) -> bool: ...

    async def soft_delete_for_owner(
        self, owner_type: str, owner_id: str, actor_id: str, when: dt.datetime
    ) -> list[str]: ...

    async def rebind_to_comment(
        self,
        attachment_ids: Sequence[str],
        *,
        project_id: str,
        work_item_id: str,
        comment_id: str,
    ) -> int: ...

    async def all_rows(self, project_id: str | None = None) -> AttachmentList: ...


class ArtifactRepository(Protocol):
    async def add(self, artifact: Artifact) -> None: ...

    async def get(self, artifact_id: str) -> Artifact | None: ...

    async def list_for_owner(
        self, project_id: str, owner_type: str, owner_id: str
    ) -> ArtifactList: ...

    async def list_for_owners(
        self, project_id: str, owner_type: str, owner_ids: Sequence[str]
    ) -> ArtifactList: ...

    async def soft_delete(self, artifact_id: str, actor_id: str, when: dt.datetime) -> bool: ...

    async def soft_delete_for_owner(
        self, owner_type: str, owner_id: str, actor_id: str, when: dt.datetime
    ) -> list[str]: ...


class WorkspaceRepository(Protocol):
    async def add(self, workspace: Workspace) -> None: ...

    async def get(self, workspace_id: str) -> Workspace | None: ...

    async def list(self, project_id: str) -> WorkspaceList: ...

    async def save(self, workspace: Workspace) -> None: ...

    async def soft_delete(self, workspace_id: str, actor_id: str, when: dt.datetime) -> bool: ...


class MailboxRepository(Protocol):
    async def add(self, mailbox: Mailbox) -> None: ...

    async def add_members(self, links: MailboxMemberList) -> None: ...

    async def get(self, mailbox_id: str) -> Mailbox | None: ...

    async def get_indiv(self, project_id: str, owner_user_id: str) -> Mailbox | None: ...

    async def get_group_by_name(self, project_id: str, name: str) -> Mailbox | None: ...

    async def list_members(self, mailbox_id: str) -> MailboxMemberList: ...


class MessageRepository(Protocol):
    async def add_message(self, message: Message) -> None: ...

    async def add_deliveries(self, rows: DeliveryList) -> None: ...

    async def add_refs(self, refs: MessageRefList) -> None: ...

    async def get_message(self, message_id: str) -> Message | None: ...

    async def list_deliveries(
        self,
        recipient_user_id: str,
        *,
        project_id: str | None = None,
        since_id: str | None = None,
        unread_only: bool = False,
        limit: int = 20,
    ) -> DeliveryList: ...

    async def list_deliveries_for_users(
        self,
        recipient_user_ids: Sequence[str],
        *,
        project_id: str | None = None,
        since_id: str | None = None,
        unread_only: bool = False,
        limit: int = 20,
    ) -> DeliveryList: ...

    async def list_deliveries_by_ids(
        self, delivery_ids: Sequence[str], *, project_id: str | None = None
    ) -> DeliveryList: ...

    async def list_messages(self, message_ids: Sequence[str]) -> MessageList: ...

    async def list_refs(self, message_ids: Sequence[str]) -> MessageRefList: ...

    async def unread_count(
        self, recipient_user_id: str, *, project_id: str | None = None
    ) -> int: ...

    async def unread_count_for_users(
        self, recipient_user_ids: Sequence[str], *, project_id: str | None = None
    ) -> int: ...

    async def mark_read(
        self,
        recipient_user_id: str,
        delivery_ids: Sequence[str],
        when: dt.datetime,
        *,
        project_id: str | None = None,
    ) -> int: ...

    async def mark_read_for_users(
        self,
        recipient_user_ids: Sequence[str],
        delivery_ids: Sequence[str],
        when: dt.datetime,
        *,
        project_id: str | None = None,
    ) -> int: ...


class OutboxRepository(Protocol):
    async def add(self, row: OutboxRow) -> None: ...

    async def claim_due(self, now: dt.datetime, limit: int) -> list[OutboxRow]:
        """pending & due rows flip to delivering inside this transaction."""
        ...

    async def mark_delivered(self, row_id: str, now: dt.datetime) -> None: ...

    async def mark_failure(
        self, row_id: str, attempts: int, next_at: dt.datetime, error: str, now: dt.datetime
    ) -> None: ...

    async def mark_failed(
        self, row_id: str, attempts: int, error: str, now: dt.datetime
    ) -> None: ...

    async def reclaim_delivering(self, now: dt.datetime) -> int: ...

    async def status_counts(self) -> dict[str, int]: ...

    async def oldest_pending_at(self) -> dt.datetime | None: ...


class EventStore(Protocol):
    async def append(
        self,
        *,
        org_id: str,
        project_id: str | None,
        seq: int,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: EventType,
        actor_user_id: str | None,
        payload: dict[str, Any],
        occurred_at: dt.datetime | None = None,
    ) -> int:
        """Append an event inside the current transaction; returns event id."""
        ...

    async def list_for_work_item(
        self,
        *,
        project_id: str,
        work_item_id: str,
        limit: int,
        before_seq: int | None = None,
    ) -> list[EventRecord]: ...


class NotificationRepository(Protocol):
    async def add(self, notification: Notification) -> None: ...

    async def list_for_user(
        self,
        recipient_user_id: str,
        *,
        unread_only: bool = False,
        project_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NotificationList: ...

    async def count_for_user(
        self,
        recipient_user_id: str,
        *,
        unread_only: bool = False,
        project_id: str | None = None,
    ) -> int: ...

    async def unread_count(
        self, recipient_user_id: str, *, project_id: str | None = None
    ) -> int: ...

    async def mark_read(self, recipient_user_id: str, ids: list[str], when: dt.datetime) -> int: ...

    async def mark_all_read(
        self,
        recipient_user_id: str,
        when: dt.datetime,
        *,
        project_id: str | None = None,
    ) -> int: ...


class UnitOfWork(Protocol):
    organizations: OrganizationRepository
    projects: ProjectRepository
    users: UserRepository
    memberships: MembershipRepository
    tokens: TokenRepository
    password_tickets: PasswordTicketRepository
    oauth_clients: OAuthClientRepository
    oauth_codes: AuthorizationCodeRepository
    oauth_consents: ConsentRepository
    oauth_login_tickets: LoginTicketRepository
    work_items: WorkItemRepository
    sprints: SprintRepository
    sprint_items: SprintItemRepository
    mailboxes: MailboxRepository
    messages: MessageRepository
    comments: CommentRepository
    attachments: AttachmentRepository
    artifacts: ArtifactRepository
    workspaces: WorkspaceRepository
    outboxes: OutboxRepository
    notifications: NotificationRepository
    events: EventStore

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(self, *exc: object) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def flush(self) -> None: ...

    async def allocate_event_seq(self, org_id: str) -> int:
        """UPDATE organization SET event_seq = event_seq + 1 ... RETURNING event_seq."""
        ...

    async def allocate_display_no(self, project_id: str) -> int:
        """UPDATE project SET item_seq = item_seq + 1 ... RETURNING item_seq."""
        ...
