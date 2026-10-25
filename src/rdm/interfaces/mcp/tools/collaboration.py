"""Artifact / attachment tools (MCP never carries binaries, mcp-tools §1.5)."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from rdm.application.services.artifact_service import ArtifactService
from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.member_service import MemberService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import artifact_out, attachment_out
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
        owner: str,
        owner_type: Literal["work_item", "comment"] = "work_item",
        project: str | None = None,
    ) -> Any:
        """列附件元数据与 download_url（不传二进制，不能上传）。

        owner 传工作项 id（KEY-42/ULID）或评论 id；跨项目时传 project key。
        """

        async def run(uow, actor):
            service = AttachmentService(uow, container.file_store)
            proj, attachments = await service.list_for(
                actor, project_key=project, owner_type=owner_type, owner_ref=owner
            )
            members = {m.id: m for m in await MemberService(uow).list_members(proj.id)}
            return ok([attachment_out(a, members) for a in attachments])

        return await run_tool(container, run)
