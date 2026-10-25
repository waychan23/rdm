"""SQLAlchemy Unit of Work.

One session/transaction per use case; a process-wide asyncio.Lock serializes
write transactions (single-writer sqlite, architecture §10). Reads should
use a plain session and need no lock.
"""

from __future__ import annotations

import asyncio
from types import TracebackType

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rdm.infrastructure.db.models import ProjectModel
from rdm.infrastructure.db.repositories.collaboration import (
    ArtifactRepository,
    AttachmentRepository,
    CommentRepository,
    WorkspaceRepository,
)
from rdm.infrastructure.db.repositories.event_store import EventStore
from rdm.infrastructure.db.repositories.mailbox import (
    MailboxRepository,
    MessageRepository,
)
from rdm.infrastructure.db.repositories.member import MemberRepository, TokenRepository
from rdm.infrastructure.db.repositories.project import ProjectRepository
from rdm.infrastructure.db.repositories.sprint import (
    SprintItemRepository,
    SprintRepository,
)
from rdm.infrastructure.db.repositories.work_item import WorkItemRepository


class SqlAlchemyUnitOfWork:
    # Class-level: one writer per process regardless of UoW instances.
    _write_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self.session: AsyncSession | None = None
        self.projects: ProjectRepository | None = None
        self.members: MemberRepository | None = None
        self.tokens: TokenRepository | None = None
        self.work_items: WorkItemRepository | None = None
        self.sprints: SprintRepository | None = None
        self.sprint_items: SprintItemRepository | None = None
        self.mailboxes: MailboxRepository | None = None
        self.messages: MessageRepository | None = None
        self.comments: CommentRepository | None = None
        self.attachments: AttachmentRepository | None = None
        self.artifacts: ArtifactRepository | None = None
        self.workspaces: WorkspaceRepository | None = None
        self.events: EventStore | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        await self._write_lock.acquire()
        try:
            # FKs are declared DEFERRABLE INITIALLY DEFERRED, so flush may
            # insert child rows before parents within one transaction;
            # enforcement happens at commit.
            self.session = self._sf()
            await self.session.begin()
            self.projects = ProjectRepository(self.session)
            self.members = MemberRepository(self.session)
            self.tokens = TokenRepository(self.session)
            self.work_items = WorkItemRepository(self.session)
            self.sprints = SprintRepository(self.session)
            self.sprint_items = SprintItemRepository(self.session)
            self.mailboxes = MailboxRepository(self.session)
            self.messages = MessageRepository(self.session)
            self.comments = CommentRepository(self.session)
            self.attachments = AttachmentRepository(self.session)
            self.artifacts = ArtifactRepository(self.session)
            self.workspaces = WorkspaceRepository(self.session)
            self.events = EventStore(self.session)
        except BaseException:
            self._write_lock.release()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self.session is not None
        try:
            if exc_type is None:
                if self.session.in_transaction():
                    await self.session.commit()
            elif self.session.in_transaction():
                await self.session.rollback()
        finally:
            await self.session.close()
            self._write_lock.release()

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()
        # Keep the unit of work usable after an explicit commit.
        await self.session.begin()

    async def rollback(self) -> None:
        assert self.session is not None
        if self.session.in_transaction():
            await self.session.rollback()

    async def flush(self) -> None:
        assert self.session is not None
        await self.session.flush()

    async def allocate_event_seq(self, project_id: str) -> int:
        assert self.session is not None
        stmt = (
            update(ProjectModel)
            .where(ProjectModel.id == project_id)
            .values(event_seq=ProjectModel.event_seq + 1)
            .returning(ProjectModel.event_seq)
        )
        seq = (await self.session.execute(stmt)).scalar_one()
        return int(seq)

    async def allocate_display_no(self, project_id: str) -> int:
        assert self.session is not None
        stmt = (
            update(ProjectModel)
            .where(ProjectModel.id == project_id)
            .values(item_seq=ProjectModel.item_seq + 1)
            .returning(ProjectModel.item_seq)
        )
        no = (await self.session.execute(stmt)).scalar_one()
        return int(no)
