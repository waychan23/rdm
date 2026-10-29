"""Integration: state transitions, gates and permissions (plan M1-2, S4/S6/S8)."""

from __future__ import annotations

import httpx

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _bootstrap_project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _create(client: httpx.AsyncClient, token: str, payload: dict, key: str = "DEMO") -> dict:
    r = await client.post(f"{API}/projects/{key}/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _user_token(
    client: httpx.AsyncClient, owner: str, name: str, roles: list[str]
) -> tuple[str, str]:
    from tests.support import make_member

    return await make_member(client, owner, "DEMO", name, roles)


async def test_task_happy_chain_and_meta(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    task = await _create(
        client, owner_token, {"kind": "task", "title": "t", "task_type": "backend"}
    )

    async def move(to: str, version: int, token: str = owner_token) -> dict:
        r = await client.post(
            f"{API}/work-items/{task['display_id']}/transition",
            json={"to": to, "row_version": version, "reason": "推进"},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text
        return r.json()

    body = await move("IN_PROGRESS", 0)
    assert body["data"]["status"] == "IN_PROGRESS"
    assert body["meta"]["allowed_transitions"] == ["TO_REVIEW", "BLOCKED", "CANCELLED"]
    assert "hint" in body["meta"]

    body = await move("TO_REVIEW", 1)
    body = await move("DONE", 2)
    assert body["data"]["status"] == "DONE"
    body = await move("PUBLISHED", 3)
    assert body["data"]["status"] == "PUBLISHED"
    # terminal state hint
    assert "终态" in body["meta"]["hint"]


async def test_illegal_transition_and_stale_version(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    task = await _create(client, owner_token, {"kind": "task", "title": "t"})

    r = await client.post(
        f"{API}/work-items/{task['display_id']}/transition",
        json={"to": "DONE", "row_version": 0},
        headers=auth(owner_token),
    )
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "WORKFLOW_ILLEGAL_TRANSITION"
    assert err["details"]["allowed_transitions"] == ["IN_PROGRESS", "CANCELLED"]

    # move forward once, then transition with stale version
    await client.post(
        f"{API}/work-items/{task['display_id']}/transition",
        json={"to": "IN_PROGRESS", "row_version": 0},
        headers=auth(owner_token),
    )
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/transition",
        json={"to": "TO_REVIEW", "row_version": 0},
        headers=auth(owner_token),
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT_VERSION"


async def test_story_gate_blocks_with_children(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    story = await _create(client, owner_token, {"kind": "story", "title": "s"})
    open_task = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "open", "parent": story["display_id"]},
    )
    done_task = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "done", "parent": story["display_id"], "task_type": "qa"},
    )
    # drive story to TO_TEST, one child DONE, one still TODO
    for ref, chain in [
        (story["display_id"], ["IN_PROGRESS", "TO_TEST"]),
        (done_task["display_id"], ["IN_PROGRESS", "TO_REVIEW", "DONE"]),
    ]:
        version = 0
        for state in chain:
            r = await client.post(
                f"{API}/work-items/{ref}/transition",
                json={"to": state, "row_version": version},
                headers=auth(owner_token),
            )
            assert r.status_code == 200, r.text
            version = r.json()["data"]["row_version"]

    r = await client.post(
        f"{API}/work-items/{story['display_id']}/transition",
        json={"to": "DONE", "row_version": 2},
        headers=auth(owner_token),
    )
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    assert details["blocking_children"] == [open_task["display_id"]]
    assert details["target"] == "DONE"
    assert details["allowed_transitions"] == ["DONE", "IN_PROGRESS", "CANCELLED"]
    assert details["hint"]

    # finish the blocking child -> gate passes
    version = 0
    for state in ["IN_PROGRESS", "TO_REVIEW", "DONE"]:
        r = await client.post(
            f"{API}/work-items/{open_task['display_id']}/transition",
            json={"to": state, "row_version": version},
            headers=auth(owner_token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.post(
        f"{API}/work-items/{story['display_id']}/transition",
        json={"to": "DONE", "row_version": 2},
        headers=auth(owner_token),
    )
    assert r.status_code == 200 and r.json()["data"]["status"] == "DONE"


async def test_worker_can_only_transition_own_item(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    _id, worker_token = await _user_token(client, owner_token, "dev", ["worker"])
    mine = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "mine", "assignee": "dev"},
    )
    other = await _create(client, owner_token, {"kind": "task", "title": "other"})

    # own item: allowed
    r = await client.post(
        f"{API}/work-items/{mine['display_id']}/transition",
        json={"to": "IN_PROGRESS", "row_version": 0},
        headers=auth(worker_token),
    )
    assert r.status_code == 200, r.text

    # someone else's item: FORBIDDEN
    r = await client.post(
        f"{API}/work-items/{other['display_id']}/transition",
        json={"to": "IN_PROGRESS", "row_version": 0},
        headers=auth(worker_token),
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_worker_cannot_self_complete_done(server, owner_token: str) -> None:
    """Review gate: even the assignee worker may not push their item to DONE."""
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    _id, worker_token = await _user_token(client, owner_token, "dev", ["worker"])
    mine = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "mine", "assignee": "dev"},
    )

    async def move(to: str, version: int) -> httpx.Response:
        return await client.post(
            f"{API}/work-items/{mine['display_id']}/transition",
            json={"to": to, "row_version": version},
            headers=auth(worker_token),
        )

    assert (await move("IN_PROGRESS", 0)).status_code == 200
    r = await move("TO_REVIEW", 1)
    assert r.status_code == 200
    blocked = await move("DONE", 2)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "FORBIDDEN"
    assert blocked.json()["error"]["details"]["target_state"] == "DONE"

    # Manager closes it after review.
    _mgr_id, mgr_token = await _user_token(client, owner_token, "tl", ["manager"])
    r = await client.post(
        f"{API}/work-items/{mine['display_id']}/transition",
        json={"to": "DONE", "row_version": 2},
        headers=auth(mgr_token),
    )
    assert r.status_code == 200, r.text

    # Issue CLOSED_DONE is a QA close-out, not a review: worker may do it.
    issue = await _create(
        client,
        owner_token,
        {"kind": "issue", "title": "bug", "assignee": "dev"},
    )
    # CLOSED_DONE carries a min_children:1 gate; give it a terminal child.
    child = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "fix", "parent": issue["display_id"]},
    )
    child_r = await client.post(
        f"{API}/work-items/{child['display_id']}/transition",
        json={"to": "IN_PROGRESS", "row_version": 0},
        headers=auth(owner_token),
    )
    child_version = child_r.json()["data"]["row_version"]
    await client.post(
        f"{API}/work-items/{child['display_id']}/transition",
        json={"to": "CANCELLED", "row_version": child_version},
        headers=auth(owner_token),
    )
    version = 0
    for to in ("TO_CONFIRM", "TO_FIX", "FIXING", "CLOSED_DONE"):
        r = await client.post(
            f"{API}/work-items/{issue['display_id']}/transition",
            json={"to": to, "row_version": version},
            headers=auth(worker_token),
        )
        assert r.status_code == 200, f"{to}: {r.text}"
        version = r.json()["data"]["row_version"]


async def test_issue_first_fix_can_close_v2(server, owner_token: str) -> None:
    """S7 first-loop: FIXING -> CLOSED_DONE with min_children gate (workflow v2)."""
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    issue = await _create(client, owner_token, {"kind": "issue", "title": "bug"})

    async def move(ref: str, to: str, version: int) -> httpx.Response:
        return await client.post(
            f"{API}/work-items/{ref}/transition",
            json={"to": to, "row_version": version},
            headers=auth(owner_token),
        )

    for idx, state in enumerate(["TO_CONFIRM", "TO_FIX", "FIXING"]):
        r = await move(issue["display_id"], state, idx)
        assert r.status_code == 200, r.text

    # CLOSED_DONE without any child task -> min_children gate
    r = await move(issue["display_id"], "CLOSED_DONE", 3)
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    assert details["min_children"] == 1 and details["child_count"] == 0

    # attach a fix task and close it, then issue closes
    fix = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "fix", "parent": issue["display_id"], "task_type": "backend"},
    )
    version = 0
    for state in ["IN_PROGRESS", "TO_REVIEW", "DONE"]:
        r = await client.post(
            f"{API}/work-items/{fix['display_id']}/transition",
            json={"to": state, "row_version": version},
            headers=auth(owner_token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]

    r = await move(issue["display_id"], "CLOSED_DONE", 3)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "CLOSED_DONE"

    # REOPEN loop still legal
    r = await move(issue["display_id"], "REOPEN", 4)
    assert r.status_code == 200
