"""FastMCP factory: register every MCP tool module (28 tools, M5)."""

from __future__ import annotations

from fastmcp import FastMCP

from rdm.interfaces.http.container import Container
from rdm.interfaces.mcp.tools import (
    collaboration as collaboration_tools,
)
from rdm.interfaces.mcp.tools import (
    comment as comment_tools,
)
from rdm.interfaces.mcp.tools import (
    mailbox as mailbox_tools,
)
from rdm.interfaces.mcp.tools import (
    member as member_tools,
)
from rdm.interfaces.mcp.tools import (
    project as project_tools,
)
from rdm.interfaces.mcp.tools import (
    sprint as sprint_tools,
)
from rdm.interfaces.mcp.tools import (
    work_item as work_item_tools,
)
from rdm.interfaces.mcp.tools import (
    workflow as workflow_tools,
)


def build_mcp(container: Container, auth) -> FastMCP:  # type: ignore[no-untyped-def]
    mcp = FastMCP("rdm", auth=auth)
    # Context tools: enhanced whoami replaces the M0 version.
    workflow_tools.register(mcp, container)
    project_tools.register(mcp, container)
    work_item_tools.register(mcp, container)
    comment_tools.register(mcp, container)
    sprint_tools.register(mcp, container)
    mailbox_tools.register(mcp, container)
    member_tools.register(mcp, container)
    collaboration_tools.register(mcp, container)
    return mcp
