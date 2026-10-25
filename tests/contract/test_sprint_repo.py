"""Contract: sprint partial unique indexes (plan M1-3)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from rdm.domain.entities import Project, Sprint, SprintItem, WorkItem
from rdm.domain.enums import SprintStatus
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


async def _project(uow: SqlAlchemyUnitOfWork) -> Project:
    p = Project(id=new_id(), key="RDM", name="RDM")
    assert uow.projects is not None
    await uow.projects.add(p)
    return p


async def _item(uow: SqlAlchemyUnitOfWork, project: Project) -> WorkItem:
    item = WorkItem(
        id=new_id(),
        project_id=project.id,
        display_no=1,
        kind="task",
        status="TODO",
        title="t",
    )
    assert uow.work_items is not None
    await uow.work_items.add(item)
    return item


async def test_two_active_sprints_violate_partial_index(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    p = await _project(uow)
    assert uow.sprints is not None
    await uow.sprints.add(
        Sprint(id=new_id(), project_id=p.id, name="a", status=SprintStatus.ACTIVE)
    )
    await uow.sprints.add(
        Sprint(id=new_id(), project_id=p.id, name="b", status=SprintStatus.ACTIVE)
    )
    with pytest.raises(IntegrityError):
        await uow.flush()
    await uow.rollback()


async def test_planned_sprints_coexist_and_active_after_reopen_ok(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    p = await _project(uow)
    assert uow.sprints is not None
    a = Sprint(id=new_id(), project_id=p.id, name="a", status=SprintStatus.PLANNED)
    b = Sprint(id=new_id(), project_id=p.id, name="b", status=SprintStatus.PLANNED)
    await uow.sprints.add(a)
    await uow.sprints.add(b)
    await uow.flush()

    rows = await uow.sprints.list(p.id)
    assert len(rows) == 2
    active = await uow.sprints.active_for_project(p.id)
    assert active is None


async def test_item_cannot_live_in_two_sprints(uow: SqlAlchemyUnitOfWork) -> None:
    p = await _project(uow)
    item = await _item(uow, p)
    assert uow.sprints is not None and uow.sprint_items is not None
    a = Sprint(id=new_id(), project_id=p.id, name="a", status=SprintStatus.PLANNED)
    b = Sprint(id=new_id(), project_id=p.id, name="b", status=SprintStatus.PLANNED)
    await uow.sprints.add(a)
    await uow.sprints.add(b)
    await uow.sprint_items.bulk_add(
        [
            SprintItem(id=new_id(), sprint_id=a.id, work_item_id=item.id),
            SprintItem(id=new_id(), sprint_id=b.id, work_item_id=item.id),
        ]
    )
    with pytest.raises(IntegrityError):
        await uow.flush()
    await uow.rollback()


async def test_active_link_for_item_and_rejoin_after_remove(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    p = await _project(uow)
    item = await _item(uow, p)
    assert uow.sprints is not None and uow.sprint_items is not None
    a = Sprint(id=new_id(), project_id=p.id, name="a", status=SprintStatus.PLANNED)
    b = Sprint(id=new_id(), project_id=p.id, name="b", status=SprintStatus.PLANNED)
    await uow.sprints.add(a)
    await uow.sprints.add(b)

    assert await uow.sprint_items.active_link_for_item(item.id) is None
    await uow.sprint_items.bulk_add(
        [SprintItem(id=new_id(), sprint_id=a.id, work_item_id=item.id)]
    )
    await uow.flush()
    link = await uow.sprint_items.active_link_for_item(item.id)
    assert link is not None and link.sprint_id == a.id

    # soft-removal frees the item to join another sprint
    assert await uow.sprint_items.remove(a.id, item.id, "owner")
    await uow.flush()
    assert await uow.sprint_items.active_link_for_item(item.id) is None
    await uow.sprint_items.bulk_add(
        [SprintItem(id=new_id(), sprint_id=b.id, work_item_id=item.id)]
    )
    await uow.flush()
    link = await uow.sprint_items.active_link_for_item(item.id)
    assert link is not None and link.sprint_id == b.id
