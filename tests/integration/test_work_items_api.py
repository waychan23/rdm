"""Integration: WorkItem REST API (plan M1-1): create/update/assign/delete/restore."""

from __future__ import annotations

import sqlite3

import httpx

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(
        f"{API}/projects",
        json={"key": key, "name": f"项目 {key}"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text


async def _make_member(
    client: httpx.AsyncClient, owner: str, project: str, name: str, roles: list[str]
) -> tuple[str, str]:
    from tests.support import make_member

    return await make_member(client, owner, project, name, roles)


async def test_create_kinds_fields_and_cross_kind_rejection(server, owner_token: str) -> None:
    client, settings, _app = server
    await _create_project(client, owner_token)

    # epic + story with story-only field
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "首个 epic"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    epic = r.json()["data"]
    assert epic["display_id"] == "DEMO-1" and epic["status"] == "TODO"

    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "story",
            "title": "用户故事",
            "parent": "DEMO-1",
            "acceptance_criteria_md": "AC",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    story = r.json()["data"]
    assert story["display_id"] == "DEMO-2"
    assert story["fields"] == {"acceptance_criteria_md": "AC"}
    assert story["parent_id"] == epic["id"]

    # issue with full kind-specific payload
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "issue",
            "title": "白屏",
            "severity": "blocker",
            "environment": "prod",
            "source_story": "DEMO-2",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    issue = r.json()["data"]
    assert issue["fields"]["severity"] == "blocker"
    assert issue["fields"]["source_story_id"] == story["id"]

    # cross-kind field -> VALIDATION_ERROR 422
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "串字段", "severity": "minor"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["field"] == "severity"

    # schema-level bad enum also 422
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "x", "task_type": "nope"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422


async def test_parent_rules(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    epic = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "epic", "title": "e"},
            headers=auth(owner_token),
        )
    ).json()["data"]

    # issue cannot have a parent
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "issue", "title": "i", "parent": epic["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"]["field"] == "parent"

    # task can hang directly under epic
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "t", "parent": "DEMO-1", "task_type": "qa"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["parent_id"] == epic["id"]

    # missing parent reference -> NOT_FOUND
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "s", "parent": "DEMO-99"},
        headers=auth(owner_token),
    )
    assert r.status_code == 404


async def test_update_optimistic_lock_and_assign(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    member_id, _tok = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    created = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": "t", "task_type": "backend"},
            headers=auth(owner_token),
        )
    ).json()["data"]
    ref = created["display_id"]

    # stale row_version -> 409 CONFLICT_VERSION
    r = await client.patch(
        f"{API}/work-items/{ref}",
        json={"row_version": 99, "title": "new"},
        headers=auth(owner_token),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT_VERSION"

    r = await client.patch(
        f"{API}/work-items/{ref}",
        json={"row_version": 0, "title": "新标题", "actual_work_hours": 2.5},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["title"] == "新标题"
    assert body["row_version"] == 1
    assert body["fields"]["actual_work_hours"] == 2.5

    # assign to member
    r = await client.post(
        f"{API}/work-items/{ref}/assign",
        json={"member": "dev"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assignee"] == {"id": member_id, "name": "dev", "type": "human"}

    # unknown assignee -> NOT_FOUND
    r = await client.post(
        f"{API}/work-items/{ref}/assign",
        json={"member": "ghost"},
        headers=auth(owner_token),
    )
    assert r.status_code == 404


async def test_detail_carries_allowed_transitions_and_children(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "e"},
        headers=auth(owner_token),
    )
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "s", "parent": "DEMO-1"},
        headers=auth(owner_token),
    )
    r = await client.get(f"{API}/work-items/DEMO-1", headers=auth(owner_token))
    assert r.status_code == 200
    payload = r.json()
    assert payload["meta"]["allowed_transitions"] == ["IN_PROGRESS", "CANCELLED"]
    assert [c["display_id"] for c in payload["meta"]["children"]] == ["DEMO-2"]


async def test_cascade_delete_and_restore_parent_chain(server, owner_token: str) -> None:
    client, settings, _app = server
    await _create_project(client, owner_token)
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "e"},
        headers=auth(owner_token),
    )
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "s", "parent": "DEMO-1"},
        headers=auth(owner_token),
    )

    r = await client.delete(f"{API}/work-items/DEMO-1", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] == ["DEMO-1", "DEMO-2"]

    assert (
        await client.get(f"{API}/work-items/DEMO-2", headers=auth(owner_token))
    ).status_code == 404

    # owner can see deleted; restoring the child alone is blocked by parent
    r = await client.get(f"{API}/work-items/DEMO-2?include_deleted=true", headers=auth(owner_token))
    assert r.status_code == 200 and r.json()["data"]["deleted_at"]
    r = await client.post(f"{API}/work-items/DEMO-2/restore", headers=auth(owner_token))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ALREADY_DELETED"

    # restore the root revives the whole batch
    r = await client.post(f"{API}/work-items/DEMO-1/restore", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["restored"] == ["DEMO-1", "DEMO-2"]
    assert (
        await client.get(f"{API}/work-items/DEMO-2", headers=auth(owner_token))
    ).status_code == 200

    # events recorded for created/assigned-less/deleted/restored
    with sqlite3.connect(settings.db_path) as conn:
        kinds = {
            row[0]
            for row in conn.execute(
                "select distinct event_type from event where aggregate_type='work_item'"
            )
        }
    assert {"work_item.created", "work_item.deleted", "work_item.restored"} <= kinds


async def test_list_filters_and_q(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    for kind, title in [("task", "登录 bug"), ("task", "登录优化"), ("epic", "支付")]:
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": kind, "title": title},
            headers=auth(owner_token),
        )
    r = await client.get(
        f"{API}/projects/DEMO/work-items?kind=task&q=登录", headers=auth(owner_token)
    )
    assert r.status_code == 200
    assert {i["display_id"] for i in r.json()["data"]} == {"DEMO-1", "DEMO-2"}

    # Multiple kinds arrive as a comma list from the backlog filter.
    r = await client.get(
        f"{API}/projects/DEMO/work-items?kind=task,epic", headers=auth(owner_token)
    )
    assert r.status_code == 200
    assert {i["display_id"] for i in r.json()["data"]} == {"DEMO-1", "DEMO-2", "DEMO-3"}

    r = await client.get(
        f"{API}/projects/DEMO/work-items?kind=task,story", headers=auth(owner_token)
    )
    assert r.status_code == 200
    assert {i["display_id"] for i in r.json()["data"]} == {"DEMO-1", "DEMO-2"}


async def test_permissions_worker_and_cross_project(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token, "DEMO")
    _id, worker_token = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    # worker cannot manage projects/members
    r = await client.post(
        f"{API}/projects",
        json={"key": "X2", "name": "x"},
        headers=auth(worker_token),
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

    # worker may create work items in own project (soft matrix)
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "mine", "task_type": "docs"},
        headers=auth(worker_token),
    )
    assert r.status_code == 201, r.text

    # cross-project access by a non-owner surfaces as NOT_FOUND
    await _create_project(client, owner_token, "OTHER")
    await client.post(
        f"{API}/projects/OTHER/work-items",
        json={"kind": "task", "title": "secret"},
        headers=auth(owner_token),
    )
    # OTHER's first item is OTHER-1 (separate item_seq per project)
    r = await client.get(f"{API}/work-items/OTHER-1", headers=auth(worker_token))
    assert r.status_code == 404


async def test_ulid_accepted_as_id(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    created = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": "by-ulid"},
            headers=auth(owner_token),
        )
    ).json()["data"]
    r = await client.get(f"{API}/work-items/{created['id']}", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.json()["data"]["display_id"] == "DEMO-1"


async def test_planned_dates_are_optional_and_clearable(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)

    # Dates are optional; when present they are plain calendar dates.
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "task",
            "title": "dated",
            "planned_start_date": "2026-11-01",
            "planned_end_date": "2026-11-15",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    item = r.json()["data"]
    assert item["planned_start_date"] == "2026-11-01"
    assert item["planned_end_date"] == "2026-11-15"

    # Malformed dates are rejected by the shared schema/service.
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "bad-date", "planned_start_date": "2026-13-01"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text

    # PATCH one date and clear the other; absent fields keep their value.
    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={"row_version": item["row_version"], "planned_end_date": None},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["planned_start_date"] == "2026-11-01"
    assert updated["planned_end_date"] is None

    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={"row_version": updated["row_version"], "planned_end_date": "2026-11-20"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["planned_end_date"] == "2026-11-20"


async def test_priority_is_mandatory_and_validated(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)

    async def create(payload: dict) -> httpx.Response:
        return await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": f"p-{payload.get('priority', 'default')}", **payload},
            headers=auth(owner_token),
        )

    # Omitted -> medium (3). 0/"unset" and out-of-range values are rejected.
    r = await create({})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["priority"] == 3
    for invalid in (0, 5):
        r = await create({"priority": invalid})
        assert r.status_code == 422, r.text

    created = {}
    for priority in (1, 2, 3, 4):
        r = await create({"priority": priority})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["priority"] == priority
        created[priority] = r.json()["data"]

    task = created[4]
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "priority": 1},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["priority"] == 1

    # Priority cannot be cleared or set outside 1..4.
    updated = r.json()["data"]
    for invalid in (0, 5, None):
        r = await client.patch(
            f"{API}/work-items/{task['display_id']}",
            json={"row_version": updated["row_version"], "priority": invalid},
            headers=auth(owner_token),
        )
        assert r.status_code == 422, r.text
