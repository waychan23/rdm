"""MCP tool catalogue and key input schemas (M6: 29 tools, §17.80/M6)."""

EXPECTED_TOOLS = {
    # 3.1 identity / context (4)
    "whoami",
    "project_get",
    "workflow_get",
    "project_bind",
    # 3.2 queries (8)
    "work_item_list",
    "work_item_get",
    "my_work_list",
    "backlog_list",
    "sprint_list",
    "sprint_get",
    "member_list",
    "comment_list",
    # 3.3 work-item writes (8)
    "work_item_create",
    "work_item_update",
    "work_item_assign",
    "work_item_transition",
    "work_item_step",
    "work_item_delete",
    "work_item_restore",
    "comment_add",
    # 3.4 sprint (4)
    "sprint_create",
    "sprint_manage",
    "sprint_start",
    "sprint_close",
    # 3.5 mailbox (3)
    "mailbox_check",
    "mailbox_send",
    "mailbox_mark_read",
    # 3.6 outputs (2)
    "artifact_add",
    "attachment_list",
}


async def test_exactly_29_tools_registered(mcp_clients) -> None:
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert len(tools) == 29


async def test_transition_schema_requires_to_and_version(mcp_clients) -> None:
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as client:
        tools = {t.name: t for t in await client.list_tools()}
    props = tools["work_item_transition"].input_schema["properties"]
    required = set(tools["work_item_transition"].input_schema.get("required", []))
    assert {"id", "to", "row_version"} <= required
    assert "reason" in props

    step_props = tools["work_item_step"].input_schema["properties"]
    step_required = set(tools["work_item_step"].input_schema.get("required", []))
    assert {"id", "action"} <= step_required
    assert {"step_key", "step_id", "executors", "note_md"} <= set(step_props)

    create_props = tools["work_item_create"].input_schema["properties"]
    # FastMCP types a plain str parameter as string; kind enum enforcement
    # lives in the shared pydantic model + service.
    assert create_props["kind"]["type"] == "string"
    assert create_props["title"]["type"] == "string"
    assert {"planned_start_date", "planned_end_date"} <= set(create_props)
    update_props = tools["work_item_update"].input_schema["properties"]
    assert {"planned_start_date", "planned_end_date"} <= set(update_props)


async def test_m2_tool_schemas(mcp_clients) -> None:
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as client:
        tools = {t.name: t for t in await client.list_tools()}

    manage_required = set(tools["sprint_manage"].input_schema.get("required", []))
    assert {"id", "action"} <= manage_required

    art_enum = tools["artifact_add"].input_schema["properties"]["owner_type"]["enum"]
    assert set(art_enum) == {"project", "item", "comment"}
    assert "url" in tools["artifact_add"].input_schema["properties"]

    assert tools["mailbox_mark_read"].input_schema["properties"]["delivery_ids"]["type"] == "array"
    assert "reply_to" in tools["mailbox_send"].input_schema["properties"]
