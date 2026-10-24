"""Contract: sprint partial unique indexes (plan M1-3)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from rdm.domain.entities import Project, Sprint
from rdm.domain.enums import SprintStatus
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


async def _project(uow: SqlAlchemyUnitOfWork) -> Project:
    p = Project(id=new_id(), key="RDM", name="RDM")
    assert uow.projects is not None
    await uow.projects.add(p)
    return p


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
