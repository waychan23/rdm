"""Integration: full-text search across work items/comments/messages/artifacts."""

from __future__ import annotations

import httpx

from tests.support import create_human, login_pat, make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def test_search_across_entities_and_permissions(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "task",
            "title": "登录预算问题",
            "description_md": "支付网关超时",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    item = r.json()["data"]
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/comments",
        json={"body_md": "支付网关需要重试"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"{API}/projects/DEMO/artifacts",
        json={
            "owner_type": "project",
            "owner_ref": "DEMO",
            "kind": "doc",
            "label": "预算设计稿",
            "url": "https://example.com/design",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    # Use a member for the message case.
    _alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={"to": ["alice"], "subject": "预算确认", "body_md": "请确认 Q4"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.get(f"{API}/search?q=预算", headers=auth(alice_token))
    assert r.status_code == 200, r.text
    hits = r.json()["data"]
    kinds = {(h["entity_type"], h["title"]) for h in hits}
    assert ("work_item", "登录预算问题") in kinds
    assert ("message", "预算确认") in kinds
    assert any(h["entity_type"] == "artifact" for h in hits)
    assert all(h["project_key"] == "DEMO" for h in hits)

    r = await client.get(f"{API}/search?q=支付网关&types=comment", headers=auth(alice_token))
    hits = r.json()["data"]
    assert len(hits) == 1
    assert hits[0]["entity_type"] == "comment"
    assert hits[0]["url"].endswith(f"/items/{item['display_id']}")

    # Project scoping and type filtering.
    r = await client.get(
        f"{API}/search?q=预算&types=work_item&project=DEMO", headers=auth(alice_token)
    )
    assert {h["entity_type"] for h in r.json()["data"]} == {"work_item"}

    # A user outside the project sees nothing.
    await create_human(client, owner_token, "outsider")
    outsider_token = await login_pat(client, "outsider")
    r = await client.get(f"{API}/search?q=预算", headers=auth(outsider_token))
    assert r.status_code == 200
    assert r.json()["data"] == []

    # Soft-deleted items disappear from the index.
    r = await client.delete(f"{API}/work-items/{item['display_id']}", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    r = await client.get(f"{API}/search?q=登录预算&types=work_item", headers=auth(alice_token))
    assert r.json()["data"] == []
