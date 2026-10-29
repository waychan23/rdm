"""M5 project binding: options, persist document, rebind, and recovery hints."""

from __future__ import annotations

from tests.mcp.mcp_helpers import call
from tests.support import add_to_project, create_human, login_pat


async def _multi_project_user(rest, owner_token: str) -> str:
    for key in ("ALT", "DEMO"):
        response = await rest.post(
            "/api/v1/projects", json={"key": key, "name": key}, headers=_hdr(owner_token)
        )
        assert response.status_code == 201, response.text
    user_id = await create_human(rest, owner_token, "multi")
    await add_to_project(rest, owner_token, "ALT", user_id, ["worker"])
    await add_to_project(rest, owner_token, "DEMO", user_id, ["worker"])
    return await login_pat(rest, "multi")


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_project_bind_returns_options_and_persist(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])

    async with mcp_clients["client_for"](token) as client:
        listed = await call(client, "project_bind", {})
        assert not listed["_is_error"], listed
        assert listed["data"]["project"] is None
        assert {item["key"] for item in listed["data"]["options"]} == {"ALT", "DEMO"}

        bound = await call(client, "project_bind", {"project": "DEMO"})
        assert not bound["_is_error"], bound
        assert bound["data"]["use_project"] == "DEMO"
        assert bound["data"]["persist"] == {
            "path": ".rdm/project.json",
            "content": {"version": 1, "project": "DEMO"},
            "action": "write",
            "required": True,
        }


async def test_project_bind_rejects_unknown_project_with_recovery(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])

    async with mcp_clients["client_for"](token) as client:
        result = await call(client, "project_bind", {"project": "NOPE"})
        assert result["_is_error"], result
        details = result["error"]["details"]
        assert details["code"] == "PROJECT_BINDING_INVALID"
        assert {item["key"] for item in details["options"]} == {"ALT", "DEMO"}
        assert details["recovery"]["steps"]
        assert "不要静默切换到其他项目" in details["recovery"]["do_not"]


async def test_project_bind_rebind_reports_change(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])

    async with mcp_clients["client_for"](token) as client:
        changed = await call(client, "project_bind", {"project": "DEMO", "current": "ALT"})
        assert not changed["_is_error"], changed
        assert changed["data"]["change"] == {
            "from": "ALT",
            "to": "DEMO",
            "from_status": None,
        }
        assert changed["data"]["requires_confirmation"] is True

        unchanged = await call(client, "project_bind", {"project": "DEMO", "current": "DEMO"})
        assert not unchanged["_is_error"], unchanged
        assert unchanged["data"]["already_bound"] is True
        assert unchanged["data"]["persist"]["required"] is False


async def test_project_bind_stale_current_returns_options(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])

    async with mcp_clients["client_for"](token) as client:
        result = await call(client, "project_bind", {"current": "NOPE"})
        assert result["_is_error"], result
        details = result["error"]["details"]
        assert details["code"] == "PROJECT_BINDING_INVALID"
        assert details["status"] == "NOT_FOUND"
        assert {item["key"] for item in details["options"]} == {"ALT", "DEMO"}


async def test_project_required_carries_options_and_recovery(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])

    async with mcp_clients["client_for"](token) as client:
        missing = await call(client, "work_item_list", {})
        assert missing["_is_error"], missing
        details = missing["error"]["details"]
        assert details["code"] == "PROJECT_REQUIRED"
        assert {item["key"] for item in details["options"]} == {"ALT", "DEMO"}
        assert details["recovery"]["steps"]

        scoped = await call(client, "work_item_list", {"project": "DEMO"})
        assert not scoped["_is_error"], scoped


async def test_single_project_still_auto_resolves(server, mcp_clients) -> None:
    rest, _settings, _app = server
    await mcp_clients["create_project"]("DEMO")
    _, token = await mcp_clients["make_member"]("solo", ["worker"], "DEMO")

    async with mcp_clients["client_for"](token) as client:
        result = await call(client, "work_item_list", {})
        assert not result["_is_error"], result
        assert result["data"] == []


async def test_project_bind_rejects_archived_project(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])
    archived = await rest.post(
        "/api/v1/projects/DEMO/archive", headers=_hdr(mcp_clients["owner_token"])
    )
    assert archived.status_code == 200, archived.text

    async with mcp_clients["client_for"](token) as client:
        result = await call(client, "project_bind", {"project": "DEMO"})
        assert result["_is_error"], result
        details = result["error"]["details"]
        assert details["code"] == "PROJECT_BINDING_INVALID"
        assert details["status"] == "ARCHIVED"
        assert {item["key"] for item in details["options"]} == {"ALT"}


async def test_whoami_includes_project_hint(server, mcp_clients) -> None:
    rest, _settings, _app = server
    token = await _multi_project_user(rest, mcp_clients["owner_token"])

    async with mcp_clients["client_for"](token) as client:
        who = await call(client, "whoami", {})
        assert not who["_is_error"], who
        assert ".rdm/project.json" in who["data"]["project_hint"]
