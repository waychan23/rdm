"""Contract: M1-1 WorkItemRepository additions (display_no, by_ids, q, restore)."""

from __future__ import annotations

from rdm.domain.entities import IssueFields, Project, StoryFields, TaskFields, WorkItem
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


def _project() -> Project:
    return Project(id=new_id(), key="RDM", name="RDM")


def _item(no: int, title: str, kind: str = "task", parent_id: str | None = None) -> WorkItem:
    fields = {
        "story": StoryFields(acceptance_criteria_md="ac"),
        "issue": IssueFields(severity="minor"),
        "task": TaskFields(task_type="qa"),
    }.get(kind)
    return WorkItem(
        id=new_id(),
        project_id=None,  # replaced by caller
        display_no=no,
        kind=kind,
        status="TODO",
        title=title,
        parent_id=parent_id,
        fields=fields,
    )


async def test_get_by_display_no_and_list_by_ids(uow: SqlAlchemyUnitOfWork) -> None:
    p = _project()
    await uow.projects.add(p)
    a, b = _item(1, "alpha"), _item(2, "beta", kind="story")
    a.project_id = b.project_id = p.id
    await uow.work_items.add(a)
    await uow.work_items.add(b)
    await uow.flush()

    got = await uow.work_items.get_by_display_no(p.id, 2)
    assert got is not None
    assert got.id == b.id
    assert got.fields == StoryFields(acceptance_criteria_md="ac")
    assert await uow.work_items.get_by_display_no(p.id, 99) is None

    rows = await uow.work_items.list_by_ids(p.id, [a.id, b.id])
    assert {r.id for r in rows} == {a.id, b.id}
    assert await uow.work_items.list_by_ids(p.id, []) == []


async def test_q_title_filter(uow: SqlAlchemyUnitOfWork) -> None:
    p = _project()
    await uow.projects.add(p)
    for no, title in [(1, "登录失败"), (2, "登录页优化"), (3, "支付回调")]:
        item = _item(no, title)
        item.project_id = p.id
        await uow.work_items.add(item)
    await uow.flush()

    rows = await uow.work_items.list(p.id, q="登录")
    assert {r.display_no for r in rows} == {1, 2}


async def test_soft_delete_restore_roundtrip(uow: SqlAlchemyUnitOfWork) -> None:
    p = _project()
    await uow.projects.add(p)
    item = _item(1, "soon gone")
    item.project_id = p.id
    await uow.work_items.add(item)
    await uow.flush()

    await uow.work_items.soft_delete(item.id, "actor", cascade_ids=[])
    assert await uow.work_items.get(item.id) is None
    hidden = await uow.work_items.get(item.id, include_deleted=True)
    assert hidden is not None and hidden.deleted_by == "actor"

    assert await uow.work_items.restore([item.id]) == 1
    restored = await uow.work_items.get(item.id)
    assert restored is not None and restored.deleted_at is None


async def test_list_children_include_deleted(uow: SqlAlchemyUnitOfWork) -> None:
    p = _project()
    await uow.projects.add(p)
    parent = _item(1, "parent", kind="epic")
    parent.project_id = p.id
    child = _item(2, "child", kind="story", parent_id=parent.id)
    child.project_id = p.id
    await uow.work_items.add(parent)
    await uow.work_items.add(child)
    await uow.flush()

    await uow.work_items.soft_delete(child.id, "actor")
    assert await uow.work_items.list_children(parent.id) == []
    hidden = await uow.work_items.list_children(parent.id, include_deleted=True)
    assert [c.id for c in hidden] == [child.id]
