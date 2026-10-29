"""Mailbox tools: check / send (mark_read is REST-only in M1)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.mailbox_service import MailboxService
from rdm.interfaces.http.container import Container
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def mailbox_check(
        since: str | None = None,
        unread_only: bool = True,
        limit: int = 20,
        project: str | None = None,
    ) -> Any:
        """增量拉取我的信件（默认只拉未读）。

        把上一页响应的 next_cursor 作为 since 传回实现增量；next_cursor 为
        null 表示没有更多。不要轮询过频（开工/出错时检查即可）。
        """

        async def run(uow, actor):
            body = await MailboxService(uow).check(
                actor, since=since, unread_only=unread_only, limit=limit
            )
            return ok(body)

        return await run_tool(container, run)

    @mcp.tool
    async def mailbox_send(
        to: list[str],
        subject: str,
        body_md: str,
        cc: list[str] | None = None,
        refs: list[str] | None = None,
        reply_to: str | None = None,
        project: str | None = None,
    ) -> Any:
        """给成员或 group 信箱发信；跨 human/agent 协作的唯一通道。

        to/cc 传成员 name/id 或 group 名；refs 附工作项 id（KEY-42/ULID）。
        reply_to 传同一事项上一封信的 message_id（mailbox_check 返回的
        message_id），服务端记录 reply_to_id 形成回信链路；不要用「Re: 原题」
        另起一封新信。不要重复发送同一内容。
        """

        async def run(uow, actor):
            _proj, message, count = await MailboxService(uow).send(
                actor,
                project,
                to=to,
                cc=cc or [],
                subject=subject,
                body_md=body_md,
                refs=refs or [],
                reply_to=reply_to,
            )
            return ok(
                {
                    "message_id": message.id,
                    "reply_to_id": message.reply_to_id,
                    "deliveries": count,
                }
            )

        return await run_tool(container, run)

    @mcp.tool
    async def mailbox_mark_read(delivery_ids: list[str]) -> Any:
        """批量把信件投递标记为已读，返回更新条数。

        处理完 mailbox_check 拉到的信件后调用；delivery id 即信件条目里的
        delivery_id，不是 message id。
        """

        async def run(uow, actor):
            if not delivery_ids:
                from rdm.domain.errors import ValidationError

                raise ValidationError("delivery_ids 至少一个", details={"field": "delivery_ids"})
            updated = await MailboxService(uow).mark_read(actor, delivery_ids)
            return ok({"updated": updated})

        return await run_tool(container, run)
