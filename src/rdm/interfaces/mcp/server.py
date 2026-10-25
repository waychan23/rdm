"""FastMCP factory: register every MCP tool module (27 tools, M2)."""

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
    sprint as sprint_tools,
)
from rdm.interfaces.mcp.tools import (
    work_item as work_item_tools,
)
from rdm.interfaces.mcp.tools import (
    workflow as workflow_tools,
)


def build_mcp(container: Container) -> FastMCP:
    mcp = FastMCP("rdm")
    # Context tools: enhanced whoami replaces the M0 version.
    workflow_tools.register(mcp, container)
    work_item_tools.register(mcp, container)
    comment_tools.register(mcp, container)
    sprint_tools.register(mcp, container)
    mailbox_tools.register(mcp, container)
    member_tools.register(mcp, container)
    collaboration_tools.register(mcp, container)
    return mcp
