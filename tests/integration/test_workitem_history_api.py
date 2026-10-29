"""Integration: work item history read model (§17.84)."""

from __future__ import annotations

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client, token: str) -> None:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text


async def _item(client, token: str, payload: dict) -> dict:
    r = await client.post(f"{API}/projects/DEMO/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_history_actions_order_and_pagination(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    epic = await _item(client, owner_token, {"kind": "epic", "title": "E"})
    story = await _item(
        client, owner_token, {"kind": "story", "title": "S", "parent": epic["display_id"]}
    )
    other = await _item(client, owner_token, {"kind": "story", "title": "S2"})

    # content edit
    r = await client.patch(
        f"{API}/work-items/{story['display_id']}",
        json={"row_version": story["row_version"], "description_md": "hello **world**"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    story = r.json()["data"]

    # status transition (pick the first allowed target)
    detail = (
        await client.get(f"{API}/work-items/{story['display_id']}", headers=auth(owner_token))
    ).json()
    target = detail["meta"]["allowed_transitions"][0]
    r = await client.post(
        f"{API}/work-items/{story['display_id']}/transition",
        json={"to": target, "row_version": story["row_version"], "reason": "开工"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    story = r.json()["data"]

    # assign
    r = await client.post(
        f"{API}/work-items/{story['display_id']}/assign",
        json={"member": "owner"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text

    # comment on the story and on another item (must not leak)
    r = await client.post(
        f"{API}/work-items/{story['display_id']}/comments",
        json={"body_md": "看这个 **截图** [link](https://x)"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    await client.post(
        f"{API}/work-items/{other['display_id']}/comments",
        json={"body_md": "unrelated"},
        headers=auth(owner_token),
    )

    r = await client.get(
        f"{API}/work-items/{story['display_id']}/history", headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    entries = body["data"]
    actions = [e["action"] for e in entries]
    assert actions[0] == "comment_created"
    assert "status_changed" in actions
    assert "assigned" in actions
    assert "content_edited" in actions
    assert actions[-1] == "created"
    assert body["meta"]["has_more"] is False
    assert all(
        e["comment"] is None or "unrelated" not in (e["comment"]["excerpt"] or "") for e in entries
    )

    status_entry = next(e for e in entries if e["action"] == "status_changed")
    assert status_entry["changes"]["status"] == {"from": "TODO", "to": target}
    assert status_entry["meta"]["reason"] == "开工"
    assert status_entry["actor"]["name"] == "owner"

    edit_entry = next(e for e in entries if e["action"] == "content_edited")
    assert edit_entry["changes"]["description_md"] == {"redacted": True}

    comment_entry = next(e for e in entries if e["action"] == "comment_created")
    assert comment_entry["comment"]["excerpt"].startswith("看这个 截图 link")

    # pagination: newest first, cursor is the last seq
    r = await client.get(
        f"{API}/work-items/{story['display_id']}/history",
        params={"limit": 2},
        headers=auth(owner_token),
    )
    page = r.json()
    assert len(page["data"]) == 2
    assert page["meta"]["has_more"] is True
    cursor = page["meta"]["next_before_seq"]
    assert cursor is not None
    r = await client.get(
        f"{API}/work-items/{story['display_id']}/history",
        params={"limit": 100, "before_seq": cursor},
        headers=auth(owner_token),
    )
    older = r.json()["data"]
    assert older and older[0]["seq"] < cursor
    assert all(e["seq"] < cursor for e in older)


async def test_history_requires_project_access(server) -> None:
    client, _settings, _app = server
    r = await client.get(f"{API}/work-items/DEMO-1/history")
    assert r.status_code == 401
