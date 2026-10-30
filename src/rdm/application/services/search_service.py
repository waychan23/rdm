"""Cross-entity full-text search use case (§17 M7)."""

from __future__ import annotations

from dataclasses import dataclass

from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.errors import ValidationError
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork

SEARCH_TYPES = ("work_item", "comment", "message", "artifact")


@dataclass(frozen=True)
class SearchHit:
    entity_type: str
    entity_id: str
    project_key: str
    ref: str
    title: str
    snippet: str
    url: str


def _snippet(title: str, body: str, query: str, width: int = 120) -> str:
    text = f"{title}\n{body}".strip()
    lowered = text.lower()
    needle = query.strip().lower()
    index = lowered.find(needle) if needle else -1
    if index < 0:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, index - width // 3)
    excerpt = text[start : start + width]
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + width < len(text) else ""
    return prefix + excerpt + suffix


class SearchService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def search(
        self,
        actor: Actor,
        query: str,
        *,
        project_key: str | None = None,
        types: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchHit]:
        query = (query or "").strip()
        if not query:
            raise ValidationError("搜索词不能为空", details={"field": "q"})
        types = types or list(SEARCH_TYPES)
        unknown = sorted(set(types) - set(SEARCH_TYPES))
        if unknown:
            raise ValidationError(
                f"未知搜索类型 {unknown!r}",
                details={"field": "types", "allowed": list(SEARCH_TYPES)},
            )
        if project_key is not None:
            scoped = await WorkItemService(self.uow).resolve_project(actor, project_key)
            project_ids = [scoped.id]
        else:
            project_ids = actor.project_ids()
        assert self.uow.search is not None and self.uow.projects is not None
        rows = await self.uow.search.search(
            project_ids,
            query,
            types=types,
            limit=max(1, min(limit, 50)),
            offset=max(0, offset),
        )
        projects = {}
        for project_id in {row.project_id for row in rows}:
            project_row = await self.uow.projects.get(project_id)
            if project_row is not None:
                projects[project_id] = project_row
        hits: list[SearchHit] = []
        for row in rows:
            hit_project = projects.get(row.project_id)
            if hit_project is None:
                continue
            display_ref = f"{hit_project.key}-{row.ref}" if row.ref else ""
            if row.entity_type in {"work_item", "comment"} and display_ref:
                url = f"/projects/{hit_project.key}/items/{display_ref}"
            elif row.entity_type == "message":
                url = f"/projects/{hit_project.key}/mailbox"
            else:
                url = f"/projects/{hit_project.key}/workspaces"
            hits.append(
                SearchHit(
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    project_key=hit_project.key,
                    ref=display_ref,
                    title=row.title or display_ref or row.entity_id,
                    snippet=_snippet(row.title, row.body, query),
                    url=url,
                )
            )
        return hits
