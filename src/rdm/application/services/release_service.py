"""Product release (version) application service (§17.121).

Lifecycle: PLANNED --publish--> RELEASED, or PLANNED --cancel--> CANCELLED.
Terminal releases are frozen. Publishing atomically walks every included
``DONE`` story to ``PUBLISHED`` through the workflow engine (gates included),
so the release timestamp and the shipped story states agree.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError

from rdm.application import security
from rdm.application.services.attachment_commit import commit_inline_images
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, Release, ReleaseItem, WorkItem
from rdm.domain.enums import ReleaseStatus
from rdm.domain.errors import (
    NotFound,
    ReleaseNameDuplicate,
    ReleaseNotReady,
    ValidationError,
)
from rdm.domain.events import EventType
from rdm.i18n import tr
from rdm.infrastructure.db.errors import translate_integrity
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.events.bus import StreamEvent, get_bus
from rdm.infrastructure.id import new_id

# Release scope is story + issue (§17.125). A story counts as ready once
# accepted (DONE) or already shipped; an issue once accepted and closed.
_RELEASE_ITEM_KINDS = {"story", "issue"}
_READY_STATUSES = {"DONE", "PUBLISHED", "CLOSED_DONE"}
# Items already shipped or abandoned cannot be newly added to a release.
_REJECTED_ITEM_STATUSES = {"PUBLISHED", "CANCELLED", "CLOSED_REJECTED"}


@dataclass(frozen=True)
class ReleaseOverview:
    project: Project
    release: Release
    items: list[WorkItem]
    status_counts: dict[str, int]
    stats: dict[str, int]
    blocking: list[WorkItem]

    @property
    def can_publish(self) -> bool:
        return (
            self.release.status == ReleaseStatus.PLANNED and bool(self.items) and not self.blocking
        )


def release_stats(statuses: Sequence[str]) -> dict[str, int]:
    total = len(statuses)
    done = sum(1 for status in statuses if status in _READY_STATUSES)
    published = sum(1 for status in statuses if status == "PUBLISHED")
    cancelled = sum(1 for status in statuses if status == "CANCELLED")
    percent = 0 if total == 0 else round(done * 100 / total)
    return {
        "total": total,
        "done": done,
        "published": published,
        "cancelled": cancelled,
        "percent": percent,
    }


class ReleaseService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)

    # --- reads ------------------------------------------------------------

    async def resolve_release(self, actor: Actor, release_id: str) -> tuple[Project, Release]:
        assert self.uow.releases is not None and self.uow.projects is not None
        release = await self.uow.releases.get(release_id)
        if release is None:
            raise NotFound(
                tr("release.not_found", default="版本 {id} 不存在", id=release_id),
                details={"release_id": release_id},
            )
        security.assert_project_access(actor, release.project_id)
        project = await self.uow.projects.get(release.project_id)
        assert project is not None
        return project, release

    async def list_releases(
        self, actor: Actor, project_key: str | None = None, status: str | None = None
    ) -> tuple[Project, list[Release], dict[str, dict[str, int]]]:
        project = await self.items.resolve_project(actor, project_key)
        assert self.uow.releases is not None and self.uow.release_items is not None
        if status is not None:
            status = status.upper()
            if status not in {s.value for s in ReleaseStatus}:
                raise ValidationError(
                    tr(
                        "release.status_invalid",
                        default="release status 必须是 PLANNED/RELEASED/CANCELLED，收到 {status!r}",
                        status=status,
                    ),
                    details={"field": "status"},
                )
        releases = await self.uow.releases.list(project.id, status=status)
        rows = await self.uow.release_items.status_rows([r.id for r in releases])
        by_release: dict[str, list[str]] = {r.id: [] for r in releases}
        for release_id, item_status in rows:
            by_release.setdefault(release_id, []).append(item_status)
        return project, releases, {r.id: release_stats(by_release[r.id]) for r in releases}

    async def overview(self, actor: Actor, release_id: str) -> ReleaseOverview:
        project, release = await self.resolve_release(actor, release_id)
        assert self.uow.release_items is not None and self.uow.work_items is not None
        links = await self.uow.release_items.list_for_release(release.id)
        items = (
            await self.uow.work_items.list_by_ids(project.id, [link.work_item_id for link in links])
            if links
            else []
        )
        items.sort(key=lambda item: item.display_no)
        counts: dict[str, int] = {}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        blocking = [item for item in items if item.status not in _READY_STATUSES]
        return ReleaseOverview(
            project=project,
            release=release,
            items=items,
            status_counts=counts,
            stats=release_stats([item.status for item in items]),
            blocking=blocking,
        )

    # --- writes -----------------------------------------------------------

    async def create(
        self, actor: Actor, project_key: str | None, data: dict[str, Any]
    ) -> tuple[Project, Release]:
        project = await self.items.resolve_project(actor, project_key)
        security.require_owner_or_manager(
            actor, project.id, tr("release.resource_label", default="版本")
        )
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError(
                tr("release.name_required", default="name 必填"), details={"field": "name"}
            )
        if len(name) > 100:
            raise ValidationError(
                tr("release.name_too_long", default="name 最长 100 个字符"),
                details={"field": "name", "max": 100},
            )
        assert self.uow.releases is not None
        existing = await self.uow.releases.get_by_name(project.id, name)
        if existing is not None:
            raise ReleaseNameDuplicate(
                tr(
                    "release.name_duplicate",
                    default="项目 {project} 已存在版本「{name}」。",
                    project=project.key,
                    name=name,
                ),
                details={"project_id": project.id, "name": name, "release_id": existing.id},
            )
        manager_id = None
        if data.get("manager_user_id"):
            manager_id = (await self.items.resolve_member(project.id, data["manager_user_id"])).id

        release = Release(
            id=new_id(),
            project_id=project.id,
            name=name,
            description_md=data.get("description_md"),
            status=ReleaseStatus.PLANNED,
            target_date=_as_date(data.get("target_date")),
            manager_user_id=manager_id,
            created_by=actor.id,
        )
        await self.uow.releases.add(release)
        await self._flush_translated()
        await commit_inline_images(self.uow, project.id, release.description_md)
        await self._event(
            project,
            release,
            EventType.RELEASE_CREATED,
            actor,
            {
                "snapshot": {
                    "id": release.id,
                    "name": release.name,
                    "status": str(release.status),
                    "target_date": _json_value(release.target_date),
                }
            },
        )
        return project, release

    async def update(
        self, actor: Actor, release_id: str, data: dict[str, Any]
    ) -> tuple[Project, Release]:
        project, release = await self.resolve_release(actor, release_id)
        security.require_owner_or_manager(
            actor, project.id, tr("release.resource_label", default="版本")
        )
        self._require_planned(release)
        assert self.uow.releases is not None

        changes: dict[str, list[Any]] = {}

        def track(key: str, new: Any) -> None:
            old = getattr(release, key)
            if old != new:
                changes[key] = [_json_value(old), _json_value(new)]
                setattr(release, key, new)

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise ValidationError(
                    tr("release.name_empty", default="name 不能为空"), details={"field": "name"}
                )
            if len(name) > 100:
                raise ValidationError(
                    tr("release.name_too_long", default="name 最长 100 个字符"),
                    details={"field": "name", "max": 100},
                )
            if name != release.name:
                duplicate = await self.uow.releases.get_by_name(project.id, name)
                if duplicate is not None and duplicate.id != release.id:
                    raise ReleaseNameDuplicate(
                        tr(
                            "release.name_duplicate",
                            default="项目 {project} 已存在版本「{name}」。",
                            project=project.key,
                            name=name,
                        ),
                        details={
                            "project_id": project.id,
                            "name": name,
                            "release_id": duplicate.id,
                        },
                    )
            track("name", name)
        if "description_md" in data:
            track("description_md", data["description_md"])
        if "target_date" in data:
            track("target_date", _as_date(data["target_date"]))
        if "manager_user_id" in data:
            manager_id = data["manager_user_id"] or None
            if manager_id is not None:
                manager_id = (await self.items.resolve_member(project.id, manager_id)).id
            track("manager_user_id", manager_id)

        if changes:
            await self.uow.releases.save_fields(release)
            await commit_inline_images(self.uow, project.id, release.description_md)
            await self._event(
                project, release, EventType.RELEASE_UPDATED, actor, {"changes": changes}
            )
        return project, release

    async def add_items(
        self, actor: Actor, release_id: str, item_refs: Sequence[str]
    ) -> tuple[Project, Release, list[WorkItem]]:
        project, release = await self.resolve_release(actor, release_id)
        self._require_planned(release)
        assert self.uow.release_items is not None
        existing = {
            link.work_item_id for link in await self.uow.release_items.list_for_release(release.id)
        }
        added: list[WorkItem] = []
        links: list[ReleaseItem] = []
        seen: set[str] = set()
        for ref in item_refs:
            item = await self.items.resolve_item(actor, ref)
            if item.project_id != project.id:
                raise ValidationError(
                    tr(
                        "release.item_other_project",
                        default="所选工作项不属于项目 {project}",
                        project=project.key,
                    ),
                    details={"work_item_id": item.id, "project_id": item.project_id},
                )
            display_id = self.items.display_id(project, item)
            if item.kind not in _RELEASE_ITEM_KINDS:
                raise ValidationError(
                    tr(
                        "release.kind_invalid",
                        default="只有 story/issue 可以加入版本，{display_id} 是 {kind}",
                        display_id=display_id,
                        kind=item.kind,
                    ),
                    details={"work_item_id": item.id, "kind": item.kind},
                )
            if item.status in _REJECTED_ITEM_STATUSES:
                raise ValidationError(
                    tr(
                        "release.item_status_invalid",
                        default="{display_id} 当前为 {status}，不能加入版本",
                        display_id=display_id,
                        status=item.status,
                    ),
                    details={"work_item_id": item.id, "status": item.status},
                )
            if item.id in existing or item.id in seen:
                raise ValidationError(
                    tr(
                        "release.item_already_in",
                        default="{display_id} 已在版本 {name} 中",
                        display_id=display_id,
                        name=release.name,
                    ),
                    details={"work_item_id": item.id, "release_id": release.id},
                )
            seen.add(item.id)
            added.append(item)
            links.append(
                ReleaseItem(
                    id=new_id(),
                    release_id=release.id,
                    work_item_id=item.id,
                    added_by=actor.id,
                )
            )
        if not links:
            return project, release, []
        await self.uow.release_items.bulk_add(links)
        await self._flush_translated()
        await self._event(
            project,
            release,
            EventType.RELEASE_ITEM_ADDED,
            actor,
            {"items": [self.items.display_id(project, item) for item in added]},
        )
        return project, release, added

    async def remove_item(
        self, actor: Actor, release_id: str, item_ref: str
    ) -> tuple[Project, Release, WorkItem]:
        project, release = await self.resolve_release(actor, release_id)
        self._require_planned(release)
        item = await self.items.resolve_item(actor, item_ref)
        assert self.uow.release_items is not None
        removed = await self.uow.release_items.remove(release.id, item.id, actor.id)
        display_id = self.items.display_id(project, item)
        if not removed:
            raise NotFound(
                tr(
                    "release.item_not_in",
                    default="{display_id} 不在版本 {name} 中",
                    display_id=display_id,
                    name=release.name,
                ),
                details={"release_id": release.id, "work_item_id": item.id},
            )
        await self._event(
            project, release, EventType.RELEASE_ITEM_REMOVED, actor, {"items": [display_id]}
        )
        return project, release, item

    async def publish(
        self, actor: Actor, release_id: str
    ) -> tuple[Project, Release, list[WorkItem]]:
        project, release = await self.resolve_release(actor, release_id)
        security.require_owner_or_manager(
            actor, project.id, tr("release.resource_label", default="版本")
        )
        if release.status == ReleaseStatus.RELEASED:
            raise ValidationError(
                tr(
                    "release.already_released",
                    default="版本 {name} 已发布，不能重复发布。",
                    name=release.name,
                ),
                details={"release_id": release.id, "status": str(release.status)},
            )
        if release.status == ReleaseStatus.CANCELLED:
            raise ValidationError(
                tr(
                    "release.cancelled_no_publish",
                    default="版本 {name} 已取消，不能发布。",
                    name=release.name,
                ),
                details={"release_id": release.id, "status": str(release.status)},
            )
        assert self.uow.release_items is not None and self.uow.work_items is not None
        links = await self.uow.release_items.list_for_release(release.id)
        items = (
            await self.uow.work_items.list_by_ids(project.id, [link.work_item_id for link in links])
            if links
            else []
        )
        items.sort(key=lambda item: item.display_no)
        if not items:
            raise ReleaseNotReady(
                tr(
                    "release.empty",
                    default="版本 {name} 还没有工作项，无法发布。",
                    name=release.name,
                ),
                details={"release_id": release.id, "reason": "empty", "blocking": []},
            )
        blocking = [item for item in items if item.status not in _READY_STATUSES]
        if blocking:
            blocking_refs = [self.items.display_id(project, item) for item in blocking]
            raise ReleaseNotReady(
                tr(
                    "release.not_ready",
                    default="版本 {name} 还有未完成的工作项：{items}",
                    name=release.name,
                    items=", ".join(blocking_refs),
                ),
                details={
                    "release_id": release.id,
                    "reason": "unfinished",
                    "blocking": [
                        {
                            "id": item.id,
                            "display_id": self.items.display_id(project, item),
                            "title": item.title,
                            "status": item.status,
                        }
                        for item in blocking
                    ],
                },
            )

        reason = tr(
            "release.publish_reason",
            default="随版本 {name} 发布",
            name=release.name,
        )
        for item in items:
            # Issues have no PUBLISHED state; CLOSED_DONE is already their
            # shipped state, so only accepted stories move forward.
            if item.kind != "story" or item.status != "DONE":
                continue
            # A system transition still runs the pinned workflow gate
            # (PUBLISHED requires every child to be terminal).
            await self.items.apply_system_transition(actor, item, "PUBLISHED", reason=reason)

        release.status = ReleaseStatus.RELEASED
        release.released_at = dt.datetime.now(dt.UTC)
        assert self.uow.releases is not None
        await self.uow.releases.save_status(release)
        await self.uow.flush()
        payload = {
            "snapshot": {
                "id": release.id,
                "name": release.name,
                "status": str(release.status),
                "target_date": _json_value(release.target_date),
                "released_at": release.released_at.isoformat(),
            },
            "items": [self.items.display_id(project, item) for item in items],
        }
        event_id = await self._event(project, release, EventType.RELEASE_PUBLISHED, actor, payload)
        await self._notify(project, release, event_id, "release.published", actor, payload)
        return project, release, items

    async def cancel(self, actor: Actor, release_id: str) -> tuple[Project, Release]:
        project, release = await self.resolve_release(actor, release_id)
        security.require_owner_or_manager(
            actor, project.id, tr("release.resource_label", default="版本")
        )
        self._require_planned(release)
        release.status = ReleaseStatus.CANCELLED
        assert self.uow.releases is not None
        await self.uow.releases.save_status(release)
        await self.uow.flush()
        await self._event(project, release, EventType.RELEASE_CANCELLED, actor, {})
        return project, release

    # --- internals --------------------------------------------------------

    @staticmethod
    def _require_planned(release: Release) -> None:
        if release.status != ReleaseStatus.PLANNED:
            raise ValidationError(
                tr(
                    "release.frozen",
                    default="版本 {name} 已是 {status}，不能再修改范围或字段。",
                    name=release.name,
                    status=str(release.status),
                ),
                details={"release_id": release.id, "status": str(release.status)},
            )

    async def _flush_translated(self) -> None:
        try:
            await self.uow.flush()
        except IntegrityError as exc:
            raise translate_integrity(exc) from exc

    async def _event(
        self,
        project: Project,
        release: Release,
        event_type: EventType,
        actor: Actor,
        payload: dict[str, Any],
    ) -> int:
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        event_id = await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="release",
            aggregate_id=release.id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )
        change = StreamEvent(
            event="release.changed",
            id=str(seq),
            data={
                "project_id": project.id,
                "project_key": project.key,
                "release_id": release.id,
                "event_type": event_type.value,
            },
        )
        self.uow.defer_after_commit(lambda: get_bus().publish_project(project.id, change))
        return event_id

    async def _notify(
        self,
        project: Project,
        release: Release,
        event_id: int,
        event_name: str,
        actor: Actor,
        payload: dict[str, Any],
    ) -> None:
        from rdm.application.services import webhook_notify

        await webhook_notify.notify_release(
            self.uow,
            project=project,
            release=release,
            event_id=event_id,
            event_name=event_name,
            actor=actor,
            payload=payload,
        )


def _as_date(value: Any) -> dt.date | None:
    if value is None or value == "" or isinstance(value, dt.date):
        return value or None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(
            tr(
                "release.date_invalid",
                default="target_date 必须是 YYYY-MM-DD，收到 {value!r}",
                value=value,
            ),
            details={"field": "target_date"},
        ) from exc


def _json_value(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
