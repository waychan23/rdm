"""Contract: delivery fan-out, ULID cursor, unread counts (plan M1-4)."""

from __future__ import annotations

import datetime as dt

from rdm.domain.entities import (
    Mailbox,
    Member,
    Message,
    MessageDelivery,
    Project,
)
from rdm.domain.enums import RecipientType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


async def _setup(uow: SqlAlchemyUnitOfWork) -> tuple[Project, Member, Mailbox]:
    project = Project(id=new_id(), key="RDM", name="RDM")
    member = Member(id=new_id(), project_id=project.id, type="human", name="dev")
    mailbox = Mailbox(
        id=new_id(),
        project_id=project.id,
        kind="indiv",
        owner_member_id=member.id,
    )
    assert uow.projects is not None and uow.members is not None and uow.mailboxes is not None
    await uow.projects.add(project)
    await uow.members.add(member)
    await uow.mailboxes.add(mailbox)
    return project, member, mailbox


async def _fan_out(
    uow: SqlAlchemyUnitOfWork,
    project: Project,
    mailbox: Mailbox,
    member_id: str,
    count: int,
) -> None:
    assert uow.messages is not None
    for i in range(count):
        message = Message(
            id=new_id(),
            project_id=project.id,
            from_member_id=member_id,
            subject=f"s{i}",
            body_md="b",
        )
        await uow.messages.add_message(message)
        await uow.messages.add_deliveries(
            [
                MessageDelivery(
                    id=new_id(),
                    message_id=message.id,
                    mailbox_id=mailbox.id,
                    recipient_member_id=member_id,
                    recipient_type=RecipientType.to,
                )
            ]
        )
    await uow.flush()


async def test_ulid_cursor_pagination_no_gaps_or_dupes(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    project, member, mailbox = await _setup(uow)
    await _fan_out(uow, project, mailbox, member.id, 5)
    assert uow.messages is not None

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = await uow.messages.list_deliveries(
            member.id, since_id=cursor, unread_only=False, limit=2
        )
        if not page:
            break
        pages += 1
        seen.extend(d.id for d in page)
        cursor = page[-1].id
        if pages > 5:
            raise AssertionError("pagination did not terminate")

    assert pages == 3
    assert len(seen) == 5 and len(set(seen)) == 5
    # ULID cursor ordering is lexicographic chronological.
    assert seen == sorted(seen)


async def test_unread_count_and_mark_read(uow: SqlAlchemyUnitOfWork) -> None:
    project, member, mailbox = await _setup(uow)
    await _fan_out(uow, project, mailbox, member.id, 3)
    assert uow.messages is not None
    assert await uow.messages.unread_count(member.id) == 3

    page = await uow.messages.list_deliveries(member.id, unread_only=False, limit=2)
    updated = await uow.messages.mark_read(member.id, [d.id for d in page], dt.datetime.now(dt.UTC))
    assert updated == 2
    assert await uow.messages.unread_count(member.id) == 1

    # recipient guard: marking someone else's deliveries changes nothing
    assert await uow.messages.mark_read(member.id, [new_id()], dt.datetime.now(dt.UTC)) == 0
