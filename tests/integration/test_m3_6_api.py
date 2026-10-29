"""M3.6 supporting endpoints: pagination total, assignee=me, overview, project edit/archive."""

from __future__ import annotations


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_item(client, token, key="DEMO", **overrides):
    payload = {"kind": "task", "title": "t", **overrides}
    r = await client.post(f"/api/v1/projects/{key}/work-items", headers=auth(token), json=payload)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _ensure_project(client, token, key: str = "DEMO") -> None:
    r = await client.post("/api/v1/projects", headers=auth(token), json={"key": key, "name": key})
    assert r.status_code == 201, r.text


async def test_list_returns_total_and_supports_assignee_me(server, owner_token) -> None:
    client, _settings, _app = server
    await _ensure_project(client, owner_token)
    item = await _create_item(client, owner_token, title="mine")
    await client.post(
        f"/api/v1/work-items/{item['display_id']}/assign",
        headers=auth(owner_token),
        json={"member": "me"},
    )
    await _create_item(client, owner_token, title="other")

    r = await client.get("/api/v1/projects/DEMO/work-items?limit=1", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["total"] >= 2
    assert len(body["data"]) == 1

    r = await client.get("/api/v1/projects/DEMO/work-items?assignee=me", headers=auth(owner_token))
    titles = [i["title"] for i in r.json()["data"]]
    assert "mine" in titles and "other" not in titles


async def test_overview_aggregates(server, owner_token) -> None:
    client, _settings, _app = server
    await _ensure_project(client, owner_token)
    await _create_item(client, owner_token, kind="story", title="s")
    r = await client.get("/api/v1/projects/DEMO/overview", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["by_kind"]["story"] >= 1
    assert data["members"] >= 1
    assert "by_status" in data and "my_open_items" in data


async def test_project_update_and_archive(server, owner_token) -> None:
    client, _settings, _app = server
    await _ensure_project(client, owner_token)
    r = await client.patch(
        "/api/v1/projects/DEMO",
        headers=auth(owner_token),
        json={"name": "改名项目", "description_md": "# hi"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "改名项目"

    r = await client.post("/api/v1/projects/DEMO/archive", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "archived"

    # Re-archiving is a validation error.
    r = await client.post("/api/v1/projects/DEMO/archive", headers=auth(owner_token))
    assert r.status_code == 422
