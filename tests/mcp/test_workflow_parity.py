"""S10: workflow_get MCP output == GET /api/v1/workflow (one producer)."""

from mcp_helpers import call


async def test_workflow_dto_parity(mcp_clients) -> None:
    helpers = mcp_clients
    rest = helpers["rest"]
    token = helpers["owner_token"]
    r = await rest.get("/api/v1/workflow", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    rest_dto = r.json()["data"]

    async with helpers["client_for"](token) as client:
        full = await call(client, "workflow_get", {})
        issue_only = await call(client, "workflow_get", {"kind": "issue"})

    assert full["_is_error"] is False
    assert full["data"] == rest_dto
    assert full["data"]["version"] == 2
    assert set(full["data"]["kinds"]) == {"epic", "story", "issue", "task", "sprint"}

    assert issue_only["data"] == {"version": 2, "kinds": {"issue": rest_dto["kinds"]["issue"]}}
    # v2 fix is present: FIXING may close directly.
    assert "CLOSED_DONE" in rest_dto["kinds"]["issue"]["transitions"]["FIXING"]
