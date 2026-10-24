"""whoami MCP tool — proves the full HTTP -> auth -> service chain in M0."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import member_out, project_out


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def whoami() -> dict:
        """Return the authenticated member and their project context."""
        request = get_http_request()
        member = request.scope["state"]["member"]
        async with container.uow() as uow:
            project = await uow.projects.get(member.project_id)
        return {
            "data": {
                "member": member_out(member),
                "project": project_out(project) if project else None,
            }
        }
