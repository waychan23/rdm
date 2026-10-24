"""FastMCP factory and tools registration."""

from __future__ import annotations

from fastmcp import FastMCP

from rdm.interfaces.http.container import Container
from rdm.interfaces.mcp.tools import whoami as whoami_tool


def build_mcp(container: Container) -> FastMCP:
    mcp = FastMCP("rdm")
    whoami_tool.register(mcp, container)
    return mcp
