"""Contract: webhook outbox state machine (claim/retry/fail/reclaim)."""

from __future__ import annotations

import datetime as dt

import pytest

from rdm.domain.entities import OutboxRow
from rdm.infrastructure.db.models import EventModel, ProjectModel
from rdm.infrastructure.db.repositories.outbox import OutboxRepository
from rdm.infrastructure.id import new_id


async def _seed(uow, n: int = 1) -> tuple[str, int]:
    pid, eid = new_id(), 1
    uow.session.add(
        ProjectModel(
            id=pid,
            key="DEMO",
            name="DEMO",
            status="active",
            item_seq=0,
            event_seq=0,
            created_at=dt.datetime.now(dt.UTC),
        )
    )
    uow.session.add(
        EventModel(
            id=eid,
            project_id=pid,
            seq=1,
            aggregate_type="work_item",
            aggregate_id="x",
            aggregate_version=0,
            event_type="work_item.assigned",
            actor_member_id=None,
            payload={},
            occurred_at=dt.datetime.now(dt.UTC),
        )
    )
    await uow.flush()
    return pid, eid


async def _row(pid: str, event_id: int, **kw) -> OutboxRow:
    return OutboxRow(
        id=new_id(),
        project_id=pid,
        event_id=event_id,
        target_url="https://hook.example",
        format="generic",
        payload={"event": kw.pop("event", "work_item.assigned")},
        created_at=dt.datetime.now(dt.UTC),
        **kw,
    )


async def test_claim_limits_and_flips_to_delivering(uow) -> None:
    pid, eid = await _seed(uow)
    repo = OutboxRepository(uow.session)
    for _ in range(12):
        await repo.add(await _row(pid, eid))
    await uow.flush()

    now = dt.datetime.now(dt.UTC)
    first = await repo.claim_due(now, 10)
    assert len(first) == 10
    assert all(r.status == "pending" for r in first)  # domain row pre-image
    assert all(r.logical_event == "work_item.assigned" for r in first)
    # All claimed rows are delivering in the DB; a second claim gets the rest.
    second = await repo.claim_due(now, 10)
    assert len(second) == 2
    # Delivering rows are not claimable.
    assert await repo.claim_due(now, 10) == []


async def test_failure_ladder_and_failed(uow) -> None:
    pid, eid = await _seed(uow)
    repo = OutboxRepository(uow.session)
    row = await _row(pid, eid)
    await repo.add(row)
    await uow.flush()
    now = dt.datetime.now(dt.UTC)
    claimed = await repo.claim_due(now, 10)
    rid = claimed[0].id

    at = now
    for attempt in range(1, 4):
        at += dt.timedelta(seconds=1)
        await repo.mark_failure(rid, attempt, at + dt.timedelta(minutes=attempt), "boom", at)
    counts = await repo.status_counts()
    assert counts == {"pending": 1}
    # Fourth failed attempt -> failed.
    at += dt.timedelta(seconds=1)
    await repo.mark_failed(rid, 4, "still broken", at)
    assert await repo.status_counts() == {"failed": 1}
    assert await repo.oldest_pending_at() is None


async def test_delivered_and_reclaim(uow) -> None:
    pid, eid = await _seed(uow)
    repo = OutboxRepository(uow.session)
    row = await _row(pid, eid)
    await repo.add(row)
    await uow.flush()
    now = dt.datetime.now(dt.UTC)
    rid = (await repo.claim_due(now, 10))[0].id
    await repo.mark_delivered(rid, now)
    assert await repo.status_counts() == {"delivered": 1}

    # A crashed worker leaves delivering rows; restart reclaims them.
    row2 = await _row(pid, eid)
    await repo.add(row2)
    await uow.flush()
    rid2 = (await repo.claim_due(now, 10))[0].id
    assert rid2 != rid
    assert await repo.reclaim_delivering(now) == 1
    again = await repo.claim_due(now, 10)
    assert [r.id for r in again] == [rid2]


@pytest.mark.parametrize("event_type", ["message.sent", "sprint.started"])
async def test_logical_event_mapping(uow, event_type) -> None:
    pid = new_id()
    uow.session.add(
        ProjectModel(
            id=pid,
            key="DEMO",
            name="D",
            status="active",
            item_seq=0,
            event_seq=0,
            created_at=dt.datetime.now(dt.UTC),
        )
    )
    uow.session.add(
        EventModel(
            id=99,
            project_id=pid,
            seq=1,
            aggregate_type="message",
            aggregate_id="m",
            aggregate_version=0,
            event_type=event_type,
            actor_member_id=None,
            payload={},
            occurred_at=dt.datetime.now(dt.UTC),
        )
    )
    await uow.flush()
    repo = OutboxRepository(uow.session)
    await repo.add(
        OutboxRow(
            id=new_id(),
            project_id=pid,
            event_id=99,
            target_url="https://x",
            format="generic",
            payload={},
            created_at=dt.datetime.now(dt.UTC),
        )
    )
    await uow.flush()
    claimed = await repo.claim_due(dt.datetime.now(dt.UTC), 5)
    expected = "mailbox.delivered" if event_type == "message.sent" else event_type
    assert claimed[0].logical_event == expected
