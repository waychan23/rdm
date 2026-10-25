"""Comment tool."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.comment_service import CommentService
from rdm.application.services.member_service import MemberService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import attachment_out, comment_out
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def comment_list(work_item_id: str, limit: int = 50, offset: int = 0) -> Any:
        """读某工作项下的评论（含每条评论挂载的附件元数据）。

        附件只有元数据和 download_url，二进制请走 OpenAPI/Web 下载。
        """

        async def run(uow, actor):
            service = CommentService(uow)
            proj, _item, comments = await service.list_for_item(actor, work_item_id)
            comments = comments[offset : offset + min(limit, 100)]
            members = await MemberService(uow).members_index(proj.id)
            rows = await AttachmentService(uow, container.file_store).list_for_owners(
                proj.id, "comment", [c.id for c in comments]
            )
            for att in rows:
                uploader = await uow.members.get(att.uploader_member_id)
                if uploader is not None:
                    members[uploader.id] = uploader
            by_comment: dict[str, list] = {}
            for att in rows:
                by_comment.setdefault(att.owner_id, []).append(attachment_out(att, members))
            return ok([comment_out(c, members, by_comment.get(c.id, [])) for c in comments])

        return await run_tool(container, run)

    @mcp.tool
    async def comment_add(
        work_item_id: str,
        body_md: str,
        reply_to: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> Any:
        """在工作项下发评论；@成员名 会给对方发站内信，可挂已有附件。

        附件请先通过 REST multipart 上传到该工作项
        （POST /projects/<key>/attachments, owner_type=work_item），再把
        返回的附件 id 以 attachment_ids 传入；只能挂同一工作项上未绑定其他
        评论的附件。找不到/重名的 @mention 会静默忽略并在
        meta.unresolved_mentions 返回，不要因此重发评论。不要用评论推动状态
        （状态走 work_item_transition）。
        """

        async def run(uow, actor):
            _proj, _item, comment, unresolved = await CommentService(uow, container.file_store).add(
                actor, work_item_id, body_md, reply_to, attachment_ids
            )
            project_id = comment.project_id
            members = await MemberService(uow).members_index(project_id)
            return ok(
                comment_out(comment, members),
                unresolved_mentions=unresolved,
            )

        return await run_tool(container, run)
