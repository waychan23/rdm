"""Helper for MCP tool calls returning structured content."""

from fastmcp import Client


async def call(client: Client, name: str, arguments: dict | None = None) -> dict:
    result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    content = result.structured_content
    assert isinstance(content, dict)
    content["_is_error"] = bool(result.is_error)
    return content
