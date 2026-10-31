"""Integration: reparent endpoint and detail meta (§17.85)."""

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


async def test_reparent_rules_and_meta(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    epic = await _item(client, owner_token, {"kind": "epic", "title": "E"})
    epic2 = await _item(client, owner_token, {"kind": "epic", "title": "E2"})
    story = await _item(
        client, owner_token, {"kind": "story", "title": "S", "parent": epic["display_id"]}
    )
    task = await _item(
        client, owner_token, {"kind": "task", "title": "T", "parent": story["display_id"]}
    )

    detail = (
        await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(owner_token))
    ).json()
    assert detail["meta"]["parent"]["display_id"] == story["display_id"]
    assert detail["meta"]["allowed_parent_kinds"] == ["epic", "issue", "story", "task"]
    assert detail["meta"]["allowed_child_kinds"] == ["issue", "task"]

    epic_detail = (
        await client.get(f"{API}/work-items/{epic['display_id']}", headers=auth(owner_token))
    ).json()
    assert epic_detail["meta"]["allowed_child_kinds"] == ["story", "task"]

    # A task can be created directly under an epic.
    epic_task = await _item(
        client,
        owner_token,
        {"kind": "task", "title": "E-task", "parent": epic["display_id"]},
    )
    assert epic_task["parent_id"] == epic["id"]

    # move task from story -> under another story
    story2 = await _item(
        client, owner_token, {"kind": "story", "title": "S2", "parent": epic2["display_id"]}
    )
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/reparent",
        json={"parent": story2["display_id"], "row_version": task["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    moved = r.json()["data"]
    assert moved["parent_id"] == story2["id"]
    assert r.json()["meta"]["changed"] is True

    # same parent -> no-op
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/reparent",
        json={"parent": story2["display_id"], "row_version": moved["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert r.json()["meta"]["changed"] is False

    # cycle: put story2 under its own descendant task
    r = await client.post(
        f"{API}/work-items/{story2['display_id']}/reparent",
        json={"parent": task["display_id"], "row_version": story2["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    # invalid kind: epic cannot be a child
    r = await client.post(
        f"{API}/work-items/{epic2['display_id']}/reparent",
        json={"parent": epic["display_id"], "row_version": epic2["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422

    # stale row_version
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/reparent",
        json={"parent": None, "row_version": task["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT_VERSION"

    # clear parent
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/reparent",
        json={"parent": None, "row_version": moved["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["parent_id"] is None

    # history recorded the reparent as an update
    hist = (
        await client.get(
            f"{API}/work-items/{task['display_id']}/history", headers=auth(owner_token)
        )
    ).json()["data"]
    assert any(e["action"] == "updated" and "parent_id" in e["changes"] for e in hist)


async def test_source_story_update(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    story1 = await _item(client, owner_token, {"kind": "story", "title": "S1"})
    story2 = await _item(client, owner_token, {"kind": "story", "title": "S2"})
    issue = await _item(
        client,
        owner_token,
        {"kind": "issue", "title": "I", "source_story": story1["display_id"]},
    )
    assert issue["fields"]["source_story_id"] == story1["id"]

    r = await client.patch(
        f"{API}/work-items/{issue['display_id']}",
        json={"row_version": issue["row_version"], "source_story": story2["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["fields"]["source_story_id"] == story2["id"]

    r = await client.patch(
        f"{API}/work-items/{issue['display_id']}",
        json={"row_version": updated["row_version"], "source_story": None},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["fields"]["source_story_id"] is None

    r = await client.patch(
        f"{API}/work-items/{issue['display_id']}",
        json={"row_version": r.json()["data"]["row_version"], "source_story": "DEMO-999"},
        headers=auth(owner_token),
    )
    assert r.status_code == 404


async def test_issue_can_be_child_of_story_or_task(server, owner_token) -> None:
    """§17.117: defects may hang off a story or task; other parents stay invalid."""
    client, _settings, _app = server
    await _project(client, owner_token)
    epic = await _item(client, owner_token, {"kind": "epic", "title": "E"})
    story = await _item(
        client, owner_token, {"kind": "story", "title": "S", "parent": epic["display_id"]}
    )
    task = await _item(
        client, owner_token, {"kind": "task", "title": "T", "parent": story["display_id"]}
    )

    story_issue = await _item(
        client, owner_token, {"kind": "issue", "title": "SBUG", "parent": story["display_id"]}
    )
    assert story_issue["parent_id"] == story["id"]

    task_issue = await _item(
        client, owner_token, {"kind": "issue", "title": "TBUG", "parent": task["display_id"]}
    )
    assert task_issue["parent_id"] == task["id"]

    story_detail = (
        await client.get(f"{API}/work-items/{story['display_id']}", headers=auth(owner_token))
    ).json()
    assert story_detail["meta"]["allowed_child_kinds"] == ["issue", "task"]

    task_detail = (
        await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(owner_token))
    ).json()
    assert task_detail["meta"]["allowed_child_kinds"] == ["issue", "task"]

    issue_detail = (
        await client.get(f"{API}/work-items/{story_issue['display_id']}", headers=auth(owner_token))
    ).json()
    assert issue_detail["meta"]["allowed_parent_kinds"] == ["story", "task"]

    # Top-level issues remain allowed.
    top = await _item(client, owner_token, {"kind": "issue", "title": "TOP"})
    assert top["parent_id"] is None

    # Epic parents are still rejected for issues.
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "issue", "title": "BAD", "parent": epic["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
