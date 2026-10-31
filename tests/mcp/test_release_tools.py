"""MCP product release tools: create/manage/get/list/publish (§17.121)."""

from __future__ import annotations

from tests.mcp.mcp_helpers import call


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_story(rest, owner_token: str, title: str = "release story") -> dict:
    r = await rest.post(
        "/api/v1/projects",
        json={"key": "DEMO", "name": "DEMO"},
        headers=_hdr(owner_token),
    )
    assert r.status_code == 201, r.text
    r = await rest.post(
        "/api/v1/projects/DEMO/work-items",
        json={"kind": "story", "title": title, "assignee": "me"},
        headers=_hdr(owner_token),
    )
    assert r.status_code == 201, r.text
    story = r.json()["data"]
    for step in ("START", "SUBMIT_TEST", "PASS"):
        r = await rest.get(f"/api/v1/work-items/{story['display_id']}", headers=_hdr(owner_token))
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
        r = await rest.post(
            f"/api/v1/work-items/{story['display_id']}/steps/{step}",
            json={"row_version": version},
            headers=_hdr(owner_token),
        )
        assert r.status_code == 200, r.text
    r = await rest.get(f"/api/v1/work-items/{story['display_id']}", headers=_hdr(owner_token))
    assert r.json()["data"]["status"] == "DONE"
    return story


async def test_release_tools_lifecycle(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    story = await _setup_story(rest, owner)

    async with mcp_clients["client_for"](owner) as client:
        created = await call(
            client,
            "release_create",
            {
                "name": "v1.0.0",
                "project": "DEMO",
                "description_md": "first",
                "target_date": "2026-11-15",
            },
        )
        assert not created["_is_error"], created
        release = created["data"]
        assert release["status"] == "PLANNED"
        assert release["items"] == []
        rid = release["id"]

        managed = await call(
            client,
            "release_manage",
            {"id": rid, "action": "add_items", "items": [story["display_id"]]},
        )
        assert not managed["_is_error"], managed
        assert managed["meta"]["added"] == [story["display_id"]]
        assert managed["data"]["stats"]["total"] == 1
        assert managed["data"]["readiness"]["can_publish"] is True

        listed = await call(client, "release_list", {"project": "DEMO"})
        assert [row["name"] for row in listed["data"]] == ["v1.0.0"]

        got = await call(client, "release_get", {"id": rid})
        assert [row["display_id"] for row in got["data"]["items"]] == [story["display_id"]]

        published = await call(client, "release_publish", {"id": rid})
        assert not published["_is_error"], published
        assert published["data"]["status"] == "RELEASED"
        assert published["data"]["stats"]["percent"] == 100
        assert published["meta"]["published"] == [story["display_id"]]

    r = await rest.get(f"/api/v1/work-items/{story['display_id']}", headers=_hdr(owner))
    assert r.json()["data"]["status"] == "PUBLISHED"


async def test_release_publish_reports_unfinished_stories(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    r = await rest.post(
        "/api/v1/projects",
        json={"key": "DEMO", "name": "DEMO"},
        headers=_hdr(owner),
    )
    assert r.status_code == 201, r.text
    r = await rest.post(
        "/api/v1/projects/DEMO/work-items",
        json={"kind": "story", "title": "not done", "assignee": "me"},
        headers=_hdr(owner),
    )
    story = r.json()["data"]

    async with mcp_clients["client_for"](owner) as client:
        release = (await call(client, "release_create", {"name": "v2", "project": "DEMO"}))["data"]
        await call(
            client,
            "release_manage",
            {"id": release["id"], "action": "add_items", "items": [story["display_id"]]},
        )
        result = await call(client, "release_publish", {"id": release["id"]})
        assert result["_is_error"] is True
        assert result["error"]["code"] == "RELEASE_NOT_READY"
        assert result["error"]["details"]["blocking"][0]["display_id"] == story["display_id"]

        # Cancelling is the explicit way to close an abandoned release.
        cancelled = await call(client, "release_manage", {"id": release["id"], "action": "cancel"})
        assert cancelled["data"]["status"] == "CANCELLED"
