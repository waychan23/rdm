"""Integration: direct/step transitions, gates and permissions (M6)."""

from __future__ import annotations

import httpx

from tests.support import make_member

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


async def _move(
    client: httpx.AsyncClient,
    token: str,
    ref: str,
    to: str,
    version: int,
    reason: str | None = None,
) -> httpx.Response:
    return await client.post(
        f"{API}/work-items/{ref}/transition",
        json={"to": to, "row_version": version, "reason": reason},
        headers=auth(token),
    )


async def _detail(client: httpx.AsyncClient, token: str, ref: str) -> dict:
    r = await client.get(f"{API}/work-items/{ref}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def _finish_task(client: httpx.AsyncClient, token: str, ref: str) -> str:
    """Drive a task to DONE via the Code Review approval step."""
    detail = await _detail(client, token, ref)
    version = detail["data"]["row_version"]
    status = detail["data"]["status"]
    if status == "DONE":
        return version
    moves = {
        "TODO": ["IN_PROGRESS", "TO_REVIEW"],
        "IN_PROGRESS": ["TO_REVIEW"],
        "TO_REVIEW": [],
    }.get(status, [])
    for to in moves:
        r = await _move(client, token, ref, to, version)
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.patch(
        f"{API}/work-items/{ref}",
        json={"row_version": version, "review_content_md": "LGTM"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = await client.post(
        f"{API}/work-items/{ref}/steps/CODE_REVIEW",
        json={"row_version": version},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    assert active is not None
    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "reviewed"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "DONE"
    return r.json()["data"]["row_version"]


async def _user_token(
    client: httpx.AsyncClient, owner: str, name: str, roles: list[str]
) -> tuple[str, str]:
    return await make_member(client, owner, "DEMO", name, roles)


async def test_task_happy_chain_and_meta(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    task = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "t", "task_type": "backend", "assignee": "me"},
    )

    r = await _move(client, owner_token, task["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"]["status"] == "IN_PROGRESS"
    assert body["meta"]["allowed_transitions"] == ["TO_REVIEW", "BLOCKED", "CANCELLED"]
    assert "hint" in body["meta"]
    version = body["data"]["row_version"]

    r = await _move(client, owner_token, task["display_id"], "TO_REVIEW", version)
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    # TO_REVIEW -> DONE has two named steps; raw transition is rejected.
    r = await _move(client, owner_token, task["display_id"], "DONE", version)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WORKFLOW_STEP_REQUIRED"

    await _finish_task(client, owner_token, task["display_id"])
    detail = await _detail(client, owner_token, task["display_id"])
    assert detail["data"]["status"] == "DONE"
    version = detail["data"]["row_version"]
    r = await _move(client, owner_token, task["display_id"], "PUBLISHED", version)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "PUBLISHED"
    assert "终态" in r.json()["meta"]["hint"]


async def test_illegal_transition_and_stale_version(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    task = await _create(client, owner_token, {"kind": "task", "title": "t", "assignee": "me"})

    r = await _move(client, owner_token, task["display_id"], "DONE", 0)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "WORKFLOW_ILLEGAL_TRANSITION"
    assert err["details"]["allowed_transitions"] == ["IN_PROGRESS", "CANCELLED"]

    r = await _move(client, owner_token, task["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 200
    version = r.json()["data"]["row_version"]
    r = await _move(client, owner_token, task["display_id"], "TO_REVIEW", version - 1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT_VERSION"


async def test_story_gate_blocks_with_children(server, owner_token: str) -> None:
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    story = await _create(client, owner_token, {"kind": "story", "title": "s", "assignee": "me"})
    open_task = await _create(
        client,
        owner_token,
        {
            "kind": "task",
            "title": "open",
            "parent": story["display_id"],
            "assignee": "me",
        },
    )
    done_task = await _create(
        client,
        owner_token,
        {
            "kind": "task",
            "title": "done",
            "parent": story["display_id"],
            "task_type": "testing",
            "assignee": "me",
        },
    )
    # drive story to TO_TEST, one child DONE, one still TODO
    version = 0
    for to in ("IN_PROGRESS", "TO_TEST"):
        r = await _move(client, owner_token, story["display_id"], to, version)
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    await _finish_task(client, owner_token, done_task["display_id"])

    r = await _move(client, owner_token, story["display_id"], "DONE", version)
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    assert details["blocking_children"] == [open_task["display_id"]]
    assert details["target"] == "DONE"
    assert details["allowed_transitions"] == ["DONE", "IN_PROGRESS", "CANCELLED"]
    assert details["hint"]

    # finish the blocking child -> gate passes
    await _finish_task(client, owner_token, open_task["display_id"])
    r = await _move(client, owner_token, story["display_id"], "DONE", version)
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
    r = await _move(client, worker_token, mine["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 200, r.text

    # someone else's item: not the designated executor
    r = await _move(client, worker_token, other["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKFLOW_STEP_FORBIDDEN"


async def test_human_worker_can_self_complete_done(server, owner_token: str) -> None:
    """A human assignee may approve their own Code Review step (self-review)."""
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    _id, worker_token = await _user_token(client, owner_token, "dev", ["worker"])
    mine = await _create(
        client,
        owner_token,
        {"kind": "task", "title": "mine", "assignee": "dev"},
    )
    await _finish_task(client, worker_token, mine["display_id"])

    # Issue CLOSED_DONE is a QA close-out, not a review: worker may do it.
    issue = await _create(
        client,
        owner_token,
        {"kind": "issue", "title": "bug", "assignee": "dev"},
    )
    child = await _create(
        client,
        owner_token,
        {
            "kind": "task",
            "title": "fix",
            "parent": issue["display_id"],
            "assignee": "me",
        },
    )
    r = await _move(client, owner_token, child["display_id"], "CANCELLED", 0)
    assert r.status_code == 200, r.text
    version = 0
    for to in ("TO_CONFIRM", "TO_FIX", "FIXING", "CLOSED_DONE"):
        r = await _move(client, worker_token, issue["display_id"], to, version)
        assert r.status_code == 200, f"{to}: {r.text}"
        version = r.json()["data"]["row_version"]


async def test_issue_first_fix_can_close_v2(server, owner_token: str) -> None:
    """S7 first-loop: FIXING -> CLOSED_DONE with min_children gate (workflow v2)."""
    client, _s, _app = server
    await _bootstrap_project(client, owner_token)
    issue = await _create(client, owner_token, {"kind": "issue", "title": "bug", "assignee": "me"})

    version = 0
    for state in ["TO_CONFIRM", "TO_FIX", "FIXING"]:
        r = await _move(client, owner_token, issue["display_id"], state, version)
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]

    # CLOSED_DONE without any child task -> min_children gate
    r = await _move(client, owner_token, issue["display_id"], "CLOSED_DONE", version)
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    assert details["min_children"] == 1 and details["child_count"] == 0

    # attach a fix task and close it, then issue closes
    fix = await _create(
        client,
        owner_token,
        {
            "kind": "task",
            "title": "fix",
            "parent": issue["display_id"],
            "task_type": "backend",
            "assignee": "me",
        },
    )
    await _finish_task(client, owner_token, fix["display_id"])

    r = await _move(client, owner_token, issue["display_id"], "CLOSED_DONE", version)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "CLOSED_DONE"

    # REOPEN loop still legal
    version = r.json()["data"]["row_version"]
    r = await _move(client, owner_token, issue["display_id"], "REOPEN", version)
    assert r.status_code == 200
