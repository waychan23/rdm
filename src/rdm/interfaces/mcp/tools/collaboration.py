"""Artifact / attachment tools (MCP never carries binaries, mcp-tools §1.5)."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from rdm.application.services.artifact_service import ArtifactService
from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.membership_service import MembershipService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import artifact_out
from rdm.interfaces.mcp.tools._attachments import attachment_mcp_out
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def artifact_add(
        owner_type: Literal["project", "item", "comment"],
        owner: str,
        kind: Literal["link", "doc", "design", "api_doc", "repo", "other"],
        label: str,
        url: str,
        description_md: str | None = None,
        project: str | None = None,
    ) -> Any:
        """挂链接型产出物（设计稿/API 文档/仓库）到项目、工作项或评论。

        owner_type=item/comment 时 owner 传工作项/评论 id；project 时传 key。
        url 必须是 http(s)。文件不能走 MCP，请用 Web/OpenAPI 上传附件。
        """

        async def run(uow, actor):
            mapped_owner = "work_item" if owner_type == "item" else owner_type
            _proj, artifact = await ArtifactService(uow).add(
                actor,
                project,
                {
                    "owner_type": mapped_owner,
                    "owner_ref": owner,
                    "kind": kind,
                    "label": label,
                    "url": url,
                    "description_md": description_md,
                },
            )
            return ok(artifact_out(artifact))

        return await run_tool(container, run)

    @mcp.tool
    async def attachment_list(
        owner: str | None = None,
        owner_type: Literal["work_item", "comment", "project"] = "work_item",
        project: str | None = None,
    ) -> Any:
        """列附件元数据、download_url 与短时 fetch_url（不传二进制，不能上传）。

        owner 传工作项 id（KEY-42/ULID）或评论 id；owner_type=project 时
        owner 可省略（或传项目 key），返回项目级内联图片。state=temp 是
        编辑器草稿，只有 active 才是已保存内容。fetch_url 可直接用 curl
        下载（15 分钟有效），无需额外 Bearer。
        """

        async def run(uow, actor):
            service = AttachmentService(uow, container.file_store)
            proj, attachments = await service.list_for(
                actor, project_key=project, owner_type=owner_type, owner_ref=owner
            )
            members = await MembershipService(uow).users_index(proj.id)
            return ok([attachment_mcp_out(container, a, members) for a in attachments])

        return await run_tool(container, run)
