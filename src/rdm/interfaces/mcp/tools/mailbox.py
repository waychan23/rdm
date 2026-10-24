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
        project: str | None = None,
    ) -> Any:
        """给成员或 group 信箱发信；跨 human/agent 协作的唯一通道。

        to/cc 传成员 name/id 或 group 名；refs 附工作项 id（KEY-42/ULID）。
        不要重复发送同一内容，同一事项用回信（M1 回信走 OpenAPI reply_to）。
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
            )
            return ok({"message_id": message.id, "deliveries": count})

        return await run_tool(container, run)
