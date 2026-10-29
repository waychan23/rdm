"""Comment tool."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.comment_service import CommentService
from rdm.application.services.membership_service import MembershipService
from rdm.domain.attachment_policy import extract_attachment_ids
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import comment_out
from rdm.interfaces.mcp.tools._attachments import attachment_mcp_out
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
            members = await MembershipService(uow).users_index(proj.id)
            attachment_service = AttachmentService(uow, container.file_store)
            rows = await attachment_service.list_for_owners(
                proj.id, "comment", [c.id for c in comments]
            )
            inline_ids: set[str] = set()
            for comment in comments:
                inline_ids |= extract_attachment_ids(comment.body_md)
            inline_rows = (
                await uow.attachments.list_by_ids(proj.id, sorted(inline_ids), active_only=True)
                if inline_ids
                else []
            )
            for att in [*rows, *inline_rows]:
                uploader = await uow.users.get(att.uploader_user_id)
                if uploader is not None:
                    members[uploader.id] = uploader
            by_comment: dict[str, list] = {c.id: [] for c in comments}
            seen: dict[str, set[str]] = {c.id: set() for c in comments}
            for att in [*rows, *inline_rows]:
                targets = (
                    [att.owner_id]
                    if att.owner_type == "comment" and att.owner_id in by_comment
                    else [c.id for c in comments if att.id in extract_attachment_ids(c.body_md)]
                )
                for comment_id in targets:
                    if att.id in seen[comment_id]:
                        continue
                    seen[comment_id].add(att.id)
                    by_comment[comment_id].append(attachment_mcp_out(container, att, members))
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
            members = await MembershipService(uow).users_index(project_id)
            return ok(
                comment_out(comment, members),
                unresolved_mentions=unresolved,
            )

        return await run_tool(container, run)
