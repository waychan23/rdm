"""M1-5 risk-1: structured error envelopes survive streamable-http.

Every business failure must come back as an isError ToolResult whose
structured_content is the same {error:{code,message,details}} envelope REST
returns (architecture §16.23).
"""

from mcp_helpers import call


async def _make_story_with_open_task(mcp_clients, owner_client) -> tuple[str, str]:
    await mcp_clients["create_project"]("DEMO")
    epic = await call(
        owner_client, "work_item_create", {"kind": "epic", "title": "e", "project": "DEMO"}
    )
    story = await call(
        owner_client,
        "work_item_create",
        {
            "kind": "story",
            "title": "s",
            "project": "DEMO",
            "parent": epic["data"]["display_id"],
        },
    )
    story_id = story["data"]["display_id"]
    task = await call(
        owner_client,
        "work_item_create",
        {
            "kind": "task",
            "title": "t",
            "project": "DEMO",
            "parent": story_id,
            "task_type": "qa",
        },
    )
    return story_id, task["data"]["display_id"]


async def test_error_envelopes_for_not_found_conflict_forbidden_gate(
    mcp_clients,
) -> None:
    helpers = mcp_clients
    owner = helpers["owner_token"]
    async with helpers["client_for"](owner) as owner_client:
        story, _task = await _make_story_with_open_task(helpers, owner_client)

        # move story to TO_TEST
        version = 0
        for to in ("IN_PROGRESS", "TO_TEST"):
            res = await call(
                owner_client,
                "work_item_transition",
                {"id": story, "to": to, "row_version": version},
            )
            assert not res["_is_error"], res
            version = res["data"]["row_version"]

        # gate blocked with structured details
        res = await call(
            owner_client,
            "work_item_transition",
            {"id": story, "to": "DONE", "row_version": 2},
        )
        assert res["_is_error"]
        err = res["error"]
        assert err["code"] == "WORKFLOW_GATE_BLOCKED"
        assert err["details"]["blocking_children"] == [_task]
        assert err["details"]["hint"]

        # not found
        res = await call(owner_client, "work_item_get", {"id": "DEMO-999"})
        assert res["_is_error"] and res["error"]["code"] == "NOT_FOUND"

        # conflict version
        res = await call(
            owner_client,
            "work_item_transition",
            {"id": story, "to": "DONE", "row_version": 99},
        )
        assert res["_is_error"] and res["error"]["code"] == "CONFLICT_VERSION"

    # worker forbidden on someone else's item
    _id, worker_token = await helpers["make_member"]("dev", ["worker"], project="DEMO")
    async with helpers["client_for"](worker_token) as worker_client:
        res = await call(
            worker_client,
            "work_item_transition",
            {"id": story, "to": "CANCELLED", "row_version": 2},
        )
        assert res["_is_error"] and res["error"]["code"] == "FORBIDDEN"


async def test_input_validation_error_is_envelope(mcp_clients) -> None:
    helpers = mcp_clients
    await helpers["create_project"]("DEMO")
    async with helpers["client_for"](helpers["owner_token"]) as client:
        # cross-kind field -> service-level VALIDATION_ERROR
        res = await call(
            client,
            "work_item_create",
            {"kind": "story", "title": "s", "severity": "minor"},
        )
        assert res["_is_error"]
        assert res["error"]["code"] == "VALIDATION_ERROR"
        assert res["error"]["details"]["applicable_kind"] == "issue"
