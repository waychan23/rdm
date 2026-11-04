"""Organization-wide system settings (RDM-127).

``web_origin`` tells agents which Web frontend origin to use when they render
work item links. Reading is open to every organization member (agents included);
changing it requires Org Owner or user_manager, matching the other system-level
settings surfaces.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from rdm.application import security
from rdm.domain.actor import Actor
from rdm.domain.entities import Organization
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.web_origin import normalize_web_origin
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


class OrgSettingsService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def get(self, actor: Actor) -> Organization:
        assert self.uow.organizations is not None
        org = await self.uow.organizations.get(actor.org_id)
        if org is None:
            raise NotFound(
                tr("org.not_found", default="组织不存在"),
                details={"org_id": actor.org_id},
            )
        return org

    async def update(self, actor: Actor, changes: dict[str, Any]) -> Organization:
        security.require_user_manager(actor)
        org = await self.get(actor)
        if "web_origin" in changes:
            org.web_origin = _clean_origin(changes["web_origin"])
        org.updated_at = dt.datetime.now(dt.UTC)
        assert self.uow.organizations is not None
        await self.uow.organizations.update(org)
        await self.uow.flush()
        return org


def _clean_origin(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return normalize_web_origin(text)
    except ValueError as exc:
        raise ValidationError(
            tr(
                "org.web_origin_invalid",
                default=(
                    "Web 前台站点必须是 http(s)://host[:port] 形式，不能包含路径、查询或片段。"
                ),
            ),
            details={"field": "web_origin"},
        ) from exc
