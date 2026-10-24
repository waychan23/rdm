"""Ports (Protocols) for repositories, event store, clock and UoW.

Infrastructure implements these; wiring happens only in app assembly.
M0 defines ports needed by project/member/auth/work-item foundation;
M1 extends with sprint/mailbox/comment repositories.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, Protocol

from rdm.domain.entities import Member, MemberToken, Project, Sprint, SprintItem, WorkItem
from rdm.domain.events import EventType

# Type aliases: inside the Protocol bodies below, a method named `list`
# shadows the builtin, so `list[...]` annotations must use the alias.
ProjectList = list[Project]
MemberList = list[Member]
TokenList = list[MemberToken]
WorkItemList = list[WorkItem]
SprintList = list[Sprint]
SprintItemList = list[SprintItem]


class Clock(Protocol):
    def now(self) -> dt.datetime: ...


class ProjectRepository(Protocol):
    async def get(self, project_id: str) -> Project | None: ...

    async def get_by_key(self, key: str, *, include_deleted: bool = False) -> Project | None: ...

    async def add(self, project: Project) -> None: ...

    async def list_all(self, *, include_deleted: bool = False) -> ProjectList: ...


class MemberRepository(Protocol):
    async def get(self, member_id: str, *, include_deleted: bool = False) -> Member | None: ...

    async def get_by_name(
        self, project_id: str, name: str, *, include_deleted: bool = False
    ) -> Member | None: ...

    async def list_by_project(
        self, project_id: str, *, include_deleted: bool = False
    ) -> MemberList: ...

    async def add(self, member: Member) -> None: ...

    async def update(self, member: Member) -> None: ...


class TokenRepository(Protocol):
    async def add(self, token: MemberToken) -> None: ...

    async def get(self, token_id: str) -> MemberToken | None: ...

    async def get_by_hash(self, token_hash: str) -> MemberToken | None: ...

    async def list_by_member(self, member_id: str) -> TokenList: ...

    async def revoke(self, token_id: str) -> bool: ...

    async def touch_last_used(self, token_id: str, when: dt.datetime) -> None: ...


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
        status: str | None = None,
        assignee_member_id: str | None = None,
        parent_id: str | None = None,
        q: str | None = None,
        expand: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkItemList: ...

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

    async def claim(self, item_id: str, member_id: str, actor_id: str) -> bool:
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

    async def is_in_sprint(self, sprint_id: str, work_item_id: str) -> bool: ...


class EventStore(Protocol):
    async def append(
        self,
        *,
        project_id: str,
        seq: int,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: EventType,
        actor_member_id: str | None,
        payload: dict[str, Any],
        occurred_at: dt.datetime | None = None,
    ) -> int:
        """Append an event inside the current transaction; returns event id."""
        ...


class UnitOfWork(Protocol):
    projects: ProjectRepository
    members: MemberRepository
    tokens: TokenRepository
    work_items: WorkItemRepository
    sprints: SprintRepository
    sprint_items: SprintItemRepository
    events: EventStore

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(self, *exc: object) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def flush(self) -> None: ...

    async def allocate_event_seq(self, project_id: str) -> int:
        """UPDATE project SET event_seq = event_seq + 1 ... RETURNING event_seq."""
        ...

    async def allocate_display_no(self, project_id: str) -> int:
        """UPDATE project SET item_seq = item_seq + 1 ... RETURNING item_seq."""
        ...
