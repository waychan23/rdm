"""M1-5: tool catalogue and key input schemas."""

EXPECTED_TOOLS = {
    "whoami",
    "project_get",
    "workflow_get",
    "work_item_list",
    "work_item_get",
    "work_item_create",
    "work_item_update",
    "work_item_assign",
    "work_item_transition",
    "work_item_delete",
    "work_item_restore",
    "comment_add",
    "sprint_create",
    "sprint_start",
    "sprint_close",
    "mailbox_check",
    "mailbox_send",
}


async def test_exactly_17_tools_registered(mcp_clients) -> None:
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert len(tools) == 17


async def test_transition_schema_requires_to_and_version(mcp_clients) -> None:
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as client:
        tools = {t.name: t for t in await client.list_tools()}
    props = tools["work_item_transition"].input_schema["properties"]
    required = set(tools["work_item_transition"].input_schema.get("required", []))
    assert {"id", "to", "row_version"} <= required
    assert "reason" in props

    create_props = tools["work_item_create"].input_schema["properties"]
    # FastMCP types a plain str parameter as string; kind enum enforcement
    # lives in the shared pydantic model + service.
    assert create_props["kind"]["type"] == "string"
    assert create_props["title"]["type"] == "string"
