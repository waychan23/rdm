"""Product release tools: list/get/create/manage/publish (§17.121)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.membership_service import MembershipService
from rdm.application.services.release_service import ReleaseService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import release_detail_out, release_out
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    async def detail(uow, actor, release_id: str) -> dict:
        overview = await ReleaseService(uow).overview(actor, release_id)
        members = await MembershipService(uow).users_index(overview.project.id)
        return release_detail_out(overview, members)

    @mcp.tool
    async def release_list(project: str | None = None, status: str | None = None) -> Any:
        """列出版本（按创建时间倒序），可按 PLANNED/RELEASED/CANCELLED 过滤。

        每项带 stats: total/done/published/cancelled/percent，可直接判断发布就绪度。
        """

        async def run(uow, actor):
            _proj, releases, stats = await ReleaseService(uow).list_releases(
                actor, project, status=status
            )
            return ok([release_out(release, stats[release.id]) for release in releases])

        return await run_tool(container, run)

    @mcp.tool
    async def release_get(id: str) -> Any:
        """读版本详情：字段、包含的 story、stats、status_counts 与 readiness。

        readiness.blocking 列出还不能发布的 story；空数组且 status=PLANNED
        才可调用 release_publish。
        """

        async def run(uow, actor):
            return ok(await detail(uow, actor, id))

        return await run_tool(container, run)

    @mcp.tool
    async def release_create(
        name: str,
        project: str | None = None,
        description_md: str | None = None,
        target_date: str | None = None,
        manager: str | None = None,
    ) -> Any:
        """创建版本（仅 Owner/Manager）。name 是版本号/名称（如 v1.4.0），项目内唯一。

        target_date 用 YYYY-MM-DD；description_md 写发布说明。创建后状态为 PLANNED。
        """

        async def run(uow, actor):
            data = {
                "name": name,
                "description_md": description_md,
                "target_date": target_date,
                "manager_user_id": manager,
            }
            data = {k: v for k, v in data.items() if v is not None}
            _proj, release = await ReleaseService(uow).create(actor, project, data)
            return ok(await detail(uow, actor, release.id))

        return await run_tool(container, run)

    @mcp.tool
    async def release_manage(
        id: str,
        action: str,
        items: list[str] | None = None,
        item: str | None = None,
        name: str | None = None,
        description_md: str | None = None,
        target_date: str | None = None,
        manager: str | None = None,
    ) -> Any:
        """管理版本：action 必须是 add_items / remove_item / update / cancel。

        - add_items：items 传 story 的 id/显示 ID（KEY-42）列表；只接受 story，
          已完成（DONE）的 story 可加入；已发布/已取消的不能加入。
          同一 story 可以同时属于多个版本。
        - remove_item：item 传单个 story。
        - update：改 name/description_md/target_date/manager（仅 Owner/Manager）。
        - cancel：放弃版本（仅 PLANNED → CANCELLED）。
        RELEASED/CANCELLED 版本已冻结，不能再改范围。发布用 release_publish。
        """

        async def run(uow, actor):
            service = ReleaseService(uow)
            if action == "add_items":
                if not items:
                    from rdm.domain.errors import ValidationError

                    raise ValidationError("add_items 需要 items 列表", details={"field": "items"})
                _p, release, added = await service.add_items(actor, id, items)
                return ok(
                    await detail(uow, actor, release.id),
                    added=[f"{_p.key}-{i.display_no}" for i in added],
                )
            if action == "remove_item":
                if not item:
                    from rdm.domain.errors import ValidationError

                    raise ValidationError("remove_item 需要 item", details={"field": "item"})
                _p, release, removed = await service.remove_item(actor, id, item)
                return ok(
                    await detail(uow, actor, release.id),
                    removed=f"{_p.key}-{removed.display_no}",
                )
            if action == "update":
                data = {
                    k: v
                    for k, v in {
                        "name": name,
                        "description_md": description_md,
                        "target_date": target_date,
                        "manager_user_id": manager,
                    }.items()
                    if v is not None
                }
                _p, release = await service.update(actor, id, data)
                return ok(await detail(uow, actor, release.id))
            if action == "cancel":
                _p, release = await service.cancel(actor, id)
                return ok(await detail(uow, actor, release.id))
            from rdm.domain.errors import ValidationError

            raise ValidationError(
                "action 必须是 add_items/remove_item/update/cancel",
                details={"field": "action", "value": action},
            )

        return await run_tool(container, run)

    @mcp.tool
    async def release_publish(id: str) -> Any:
        """发布版本（仅 Owner/Manager）。

        要求版本为 PLANNED、至少包含一个 story，且所有 story 都是 DONE/PUBLISHED；
        否则返回 RELEASE_NOT_READY 并在 details.blocking 列出未完成项。
        成功时同一事务把所有 DONE story 推到 PUBLISHED，并置版本为 RELEASED。
        """

        async def run(uow, actor):
            _p, release, items = await ReleaseService(uow).publish(actor, id)
            return ok(
                await detail(uow, actor, release.id),
                published=[f"{_p.key}-{item.display_no}" for item in items],
            )

        return await run_tool(container, run)
