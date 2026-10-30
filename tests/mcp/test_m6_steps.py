"""M6 MCP: work_item_step named-step lifecycle."""

from __future__ import annotations

from tests.mcp.mcp_helpers import call


async def test_work_item_step_tool_flow(server, mcp_clients) -> None:
    helpers = mcp_clients
    rest = helpers["rest"]
    owner = helpers["owner_token"]
    r = await rest.post(
        "/api/v1/projects",
        json={"key": "DEMO", "name": "DEMO"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201, r.text

    async with helpers["client_for"](owner) as client:
        task = await call(
            client,
            "work_item_create",
            {
                "kind": "task",
                "title": "mcp-step",
                "project": "DEMO",
                "assignee": "me",
            },
        )
        assert not task["_is_error"], task
        ref = task["data"]["display_id"]
        version = task["data"]["row_version"]

        for to in ("IN_PROGRESS", "TO_REVIEW"):
            res = await call(
                client,
                "work_item_transition",
                {"id": ref, "to": to, "row_version": version},
            )
            assert not res["_is_error"], res
            version = res["data"]["row_version"]

        updated = await call(
            client,
            "work_item_update",
            {"id": ref, "row_version": version, "review_content_md": "LGTM"},
        )
        assert not updated["_is_error"], updated
        version = updated["data"]["row_version"]

        started = await call(
            client,
            "work_item_step",
            {
                "id": ref,
                "action": "start",
                "step_key": "CODE_REVIEW",
                "row_version": version,
            },
        )
        assert not started["_is_error"], started
        step_id = started["meta"]["active_step"]["id"]
        assert started["meta"]["active_step"]["status"] == "PENDING"

        executed = await call(
            client,
            "work_item_step",
            {
                "id": ref,
                "action": "execute",
                "step_id": step_id,
                "note_md": "reviewed in MCP",
            },
        )
        assert not executed["_is_error"], executed
        assert executed["data"]["status"] == "DONE"
        assert executed["meta"]["active_step"] is None

        detail = await call(client, "work_item_get", {"id": ref})
        assert "available_steps" in detail["meta"]
        assert "active_step" in detail["meta"]
        comments = await call(client, "comment_list", {"work_item_id": ref})
        assert any(c["body_md"] == "reviewed in MCP" for c in comments["data"])
