"""SQLAlchemy Unit of Work.

One session/transaction per use case; a process-wide asyncio.Lock serializes
write transactions (single-writer sqlite, architecture §10). Reads should
use a plain session and need no lock.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from weakref import WeakKeyDictionary

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rdm.infrastructure.db.models import OrganizationModel, ProjectModel
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
from rdm.infrastructure.db.repositories.membership import MembershipRepository
from rdm.infrastructure.db.repositories.notification import NotificationRepository
from rdm.infrastructure.db.repositories.oauth import (
    AuthorizationCodeRepository,
    ConsentRepository,
    LoginTicketRepository,
    OAuthClientRepository,
)
from rdm.infrastructure.db.repositories.organization import OrganizationRepository
from rdm.infrastructure.db.repositories.outbox import OutboxRepository
from rdm.infrastructure.db.repositories.project import ProjectRepository
from rdm.infrastructure.db.repositories.search import SearchRepository
from rdm.infrastructure.db.repositories.sprint import (
    SprintItemRepository,
    SprintRepository,
)
from rdm.infrastructure.db.repositories.user import (
    PasswordTicketRepository,
    TokenRepository,
    UserRepository,
)
from rdm.infrastructure.db.repositories.work_item import WorkItemRepository
from rdm.infrastructure.db.repositories.work_item_people import WorkItemPeopleRepository
from rdm.infrastructure.db.repositories.work_item_step import WorkItemStepRepository


class SqlAlchemyUnitOfWork:
    # One writer per running event loop. Keying the lock by loop keeps the
    # production guarantee (a single process/loop = a single write lock)
    # while avoiding a 3.13 pitfall: an asyncio.Lock binds to the loop of
    # its first contended acquire and then refuses every other loop. A
    # class-level lock created at import time would therefore cross event
    # loops (tests create one per test; a worker cancelled mid-transaction
    # can leave it held on a loop that is about to close).
    _locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()

    @classmethod
    def _write_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = cls._locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[loop] = lock
        return lock

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self.session: AsyncSession | None = None
        self.organizations: OrganizationRepository | None = None
        self.projects: ProjectRepository | None = None
        self.users: UserRepository | None = None
        self.memberships: MembershipRepository | None = None
        self.tokens: TokenRepository | None = None
        self.password_tickets: PasswordTicketRepository | None = None
        self.oauth_clients: OAuthClientRepository | None = None
        self.oauth_codes: AuthorizationCodeRepository | None = None
        self.oauth_consents: ConsentRepository | None = None
        self.oauth_login_tickets: LoginTicketRepository | None = None
        self.work_items: WorkItemRepository | None = None
        self.work_item_people: WorkItemPeopleRepository | None = None
        self.work_item_steps: WorkItemStepRepository | None = None
        self.sprints: SprintRepository | None = None
        self.sprint_items: SprintItemRepository | None = None
        self.mailboxes: MailboxRepository | None = None
        self.messages: MessageRepository | None = None
        self.comments: CommentRepository | None = None
        self.attachments: AttachmentRepository | None = None
        self.artifacts: ArtifactRepository | None = None
        self.workspaces: WorkspaceRepository | None = None
        self.outboxes: OutboxRepository | None = None
        self.notifications: NotificationRepository | None = None
        self.search: SearchRepository | None = None
        self.events: EventStore | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        await self._write_lock().acquire()
        try:
            # FKs are declared DEFERRABLE INITIALLY DEFERRED, so flush may
            # insert child rows before parents within one transaction;
            # enforcement happens at commit.
            self.session = self._sf()
            await self.session.begin()
            self.organizations = OrganizationRepository(self.session)
            self.projects = ProjectRepository(self.session)
            self.users = UserRepository(self.session)
            self.memberships = MembershipRepository(self.session)
            self.tokens = TokenRepository(self.session)
            self.password_tickets = PasswordTicketRepository(self.session)
            self.oauth_clients = OAuthClientRepository(self.session)
            self.oauth_codes = AuthorizationCodeRepository(self.session)
            self.oauth_consents = ConsentRepository(self.session)
            self.oauth_login_tickets = LoginTicketRepository(self.session)
            self.work_items = WorkItemRepository(self.session)
            self.work_item_people = WorkItemPeopleRepository(self.session)
            self.work_item_steps = WorkItemStepRepository(self.session)
            self.sprints = SprintRepository(self.session)
            self.sprint_items = SprintItemRepository(self.session)
            self.mailboxes = MailboxRepository(self.session)
            self.messages = MessageRepository(self.session)
            self.comments = CommentRepository(self.session)
            self.attachments = AttachmentRepository(self.session)
            self.artifacts = ArtifactRepository(self.session)
            self.workspaces = WorkspaceRepository(self.session)
            self.outboxes = OutboxRepository(self.session)
            self.notifications = NotificationRepository(self.session)
            self.search = SearchRepository(self.session)
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
            self._write_lock().release()

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

    async def allocate_event_seq(self, org_id: str) -> int:
        assert self.session is not None
        stmt = (
            update(OrganizationModel)
            .where(OrganizationModel.id == org_id)
            .values(event_seq=OrganizationModel.event_seq + 1)
            .returning(OrganizationModel.event_seq)
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
