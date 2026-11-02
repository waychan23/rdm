"""Contract suite: repositories, UoW, event store, assembly (plan M0-5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from rdm.domain.constants import DEFAULT_ORG_ID
from rdm.domain.entities import (
    IssueFields,
    Project,
    ProjectMember,
    StoryFields,
    TaskFields,
    User,
    WorkItem,
)
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


def make_project(key: str = "RDM") -> Project:
    return Project(id=new_id(), org_id=DEFAULT_ORG_ID, key=key, name=f"项目 {key}")


def make_member(name: str = "owner", **kw) -> User:
    return User(
        id=new_id(),
        org_id=DEFAULT_ORG_ID,
        type=kw.pop("type", "human"),
        name=name,
        org_roles=kw.pop("roles", []),
        **kw,
    )


def make_membership(project_id: str, user_id: str, roles: list[str]) -> ProjectMember:
    return ProjectMember(
        id=new_id(),
        org_id=DEFAULT_ORG_ID,
        project_id=project_id,
        user_id=user_id,
        roles=roles,
    )


def make_work_item(
    project_id: str,
    no: int,
    *,
    kind: str = "task",
    status: str = "TODO",
    fields=None,
    parent_id: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=new_id(),
        project_id=project_id,
        display_no=no,
        kind=kind,
        status=status,
        title=f"{kind}-{no}",
        parent_id=parent_id,
        fields=fields,
    )


async def test_project_crud_and_key_lookup(uow: SqlAlchemyUnitOfWork) -> None:
    p = make_project("DEMO")
    assert uow.projects is not None
    await uow.projects.add(p)

    assert (await uow.projects.get(p.id)).key == "DEMO"
    assert (await uow.projects.get_by_key("demo")).id == p.id  # case-insensitive
    assert [x.id for x in await uow.projects.list_all()] == [p.id]


async def test_duplicate_project_key_violates_partial_index(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    await uow.projects.add(make_project("DUP"))
    await uow.projects.add(make_project("dup"))
    with pytest.raises(IntegrityError):
        await uow.session.flush()
    await uow.rollback()


async def test_agent_member_requires_manager(uow: SqlAlchemyUnitOfWork) -> None:
    p = make_project()
    await uow.projects.add(p)
    await uow.users.add(make_member(type="agent", name="a1"))
    with pytest.raises(IntegrityError):
        await uow.session.flush()
    await uow.rollback()


async def test_member_lifecycle(uow: SqlAlchemyUnitOfWork) -> None:
    p = make_project()
    await uow.projects.add(p)
    human = make_member(name="pm")
    agent = make_member(name="dev", type="agent", manager_user_id=human.id)
    await uow.users.add(human)
    await uow.users.add(agent)
    await uow.memberships.add(make_membership(p.id, human.id, ["manager"]))
    await uow.memberships.add(make_membership(p.id, agent.id, []))

    users = await uow.users.list_by_org(DEFAULT_ORG_ID)
    assert {u.name for u in users} == {"pm", "dev"}
    assert (await uow.users.get_by_name(DEFAULT_ORG_ID, "dev")).manager_user_id == human.id
    rows = await uow.memberships.list_by_project(p.id)
    assert {r.user_id for r in rows} == {human.id, agent.id}


async def test_work_item_kind_fields_roundtrip(uow: SqlAlchemyUnitOfWork) -> None:
    p = make_project()
    await uow.projects.add(p)
    story = make_work_item(
        p.id, 1, kind="story", status="TODO", fields=StoryFields(acceptance_criteria_md="AC")
    )
    issue = make_work_item(
        p.id,
        2,
        kind="issue",
        status="OPEN",
        fields=IssueFields(severity="critical", environment="prod"),
    )
    task = make_work_item(
        p.id,
        3,
        kind="task",
        status="TODO",
        fields=TaskFields(task_type="frontend", est_work_hours=Decimal("12.5")),
    )
    for item in (story, issue, task):
        await uow.work_items.add(item)

    loaded_story = await uow.work_items.get(story.id)
    assert isinstance(loaded_story.fields, StoryFields)
    assert loaded_story.fields.acceptance_criteria_md == "AC"

    loaded_issue = await uow.work_items.get(issue.id)
    assert isinstance(loaded_issue.fields, IssueFields)
    assert loaded_issue.fields.severity == "critical"

    loaded_task = await uow.work_items.get(task.id)
    assert isinstance(loaded_task.fields, TaskFields)
    assert loaded_task.fields.est_work_hours == Decimal("12.5")

    # list() defaults to master-only assembly.
    items = await uow.work_items.list(p.id)
    assert len(items) == 3
    assert all(i.fields is None for i in items)

    expanded = await uow.work_items.list(p.id, expand=True)
    assert {type(i.fields).__name__ for i in expanded} == {
        "StoryFields",
        "IssueFields",
        "TaskFields",
    }


async def test_expand_is_batched_not_n_plus_1(uow: SqlAlchemyUnitOfWork, query_counter) -> None:
    p = make_project()
    await uow.projects.add(p)
    for no in range(5):
        await uow.work_items.add(
            make_work_item(p.id, no + 1, fields=TaskFields(task_type="backend"))
        )
    await uow.session.flush()

    query_counter["count"] = 0
    items = await uow.work_items.list(p.id, expand=True)
    assert len(items) == 5
    # 1 master query + 3 extension IN-queries, regardless of row count.
    assert query_counter["count"] <= 4, query_counter["count"]


async def test_optimistic_lock_conflict(uow: SqlAlchemyUnitOfWork) -> None:
    from rdm.domain.errors import ConflictVersion

    p = make_project()
    await uow.projects.add(p)
    item = make_work_item(p.id, 1)
    await uow.work_items.add(item)
    await uow.session.flush()

    item.title = "updated"
    await uow.work_items.save(item)  # version 0 -> 1
    stale = make_work_item(p.id, 1)  # separate object at version 0
    stale.id = item.id
    stale.row_version = 0
    stale.title = "stale write"
    with pytest.raises(ConflictVersion):
        await uow.work_items.save(stale)


async def test_claim_race_returns_false_when_already_assigned(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    p = make_project()
    await uow.projects.add(p)
    item = make_work_item(p.id, 1)
    await uow.work_items.add(item)
    m1, m2 = make_member("m1"), make_member("m2")
    await uow.users.add(m1)
    await uow.users.add(m2)

    assert await uow.work_items.claim(item.id, m1.id, m1.id) is True
    assert await uow.work_items.claim(item.id, m2.id, m2.id) is False
    loaded = await uow.work_items.get(item.id, expand=False)
    assert loaded.assignee_user_id == m1.id


async def test_event_seq_allocation_monotonic(uow: SqlAlchemyUnitOfWork) -> None:
    p = make_project()
    await uow.projects.add(p)
    await uow.session.flush()

    assert await uow.allocate_event_seq(DEFAULT_ORG_ID) == 1
    assert await uow.allocate_event_seq(DEFAULT_ORG_ID) == 2
    # Visible within the transaction on the ORM state.
    fresh = await uow.organizations.get(DEFAULT_ORG_ID)
    assert fresh.event_seq == 2


async def test_projection_and_event_rollback_together(session_factory) -> None:
    """An exception in the write path must leave neither projection nor event."""
    uow = SqlAlchemyUnitOfWork(session_factory)
    project_id: str | None = None
    item_id: str | None = None
    with pytest.raises(RuntimeError, match="boom"):
        async with uow:
            p = make_project()
            await uow.projects.add(p)
            await uow.session.flush()
            project_id = p.id
            item = make_work_item(p.id, 1)
            await uow.work_items.add(item)
            seq = await uow.allocate_event_seq(DEFAULT_ORG_ID)
            await uow.events.append(
                org_id=DEFAULT_ORG_ID,
                project_id=p.id,
                seq=seq,
                aggregate_type="work_item",
                aggregate_id=item.id,
                aggregate_version=0,
                event_type=EventType.WORK_ITEM_CREATED,
                actor_user_id=None,
                payload={"snapshot": {"id": item.id}},
            )
            item_id = item.id
            raise RuntimeError("boom")

    # Fresh session: nothing survived the rollback.
    async with session_factory() as session:
        async with session.begin():
            item_count = (
                await session.execute(text("select count(*) from work_item"))
            ).scalar_one()
            event_count = (await session.execute(text("select count(*) from event"))).scalar_one()
            project_count = (
                await session.execute(text("select count(*) from project"))
            ).scalar_one()
    assert (item_count, event_count, project_count) == (0, 0, 0)
    assert project_id and item_id


async def test_savepoint_rolls_back_only_nested_writes(uow: SqlAlchemyUnitOfWork) -> None:
    p = make_project("SP")
    await uow.projects.add(p)
    item = make_work_item(p.id, 1, kind="task")
    await uow.work_items.add(item)

    outer_calls: list[str] = []
    inner_calls: list[str] = []
    uow.defer_after_commit(lambda: outer_calls.append("outer"))

    with pytest.raises(RuntimeError):
        async with uow.savepoint():
            uow.defer_after_commit(lambda: inner_calls.append("inner"))
            item.title = "changed"
            await uow.work_items.save(item)
            raise RuntimeError("boom")

    # Only the nested write was rolled back; the outer transaction is usable.
    loaded = await uow.work_items.get(item.id)
    assert loaded is not None and loaded.title != "changed"
    loaded.title = "outer-change"
    await uow.work_items.save(loaded)
    assert (await uow.work_items.get(item.id)).title == "outer-change"

    await uow.commit()
    assert outer_calls == ["outer"]
    assert inner_calls == []
