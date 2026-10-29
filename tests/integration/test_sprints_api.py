"""Integration: sprint lifecycle (plan M1-3, S3 + close gate + permissions)."""

from __future__ import annotations

import sqlite3

import httpx

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _item(client: httpx.AsyncClient, token: str, payload: dict, key: str = "DEMO") -> dict:
    r = await client.post(f"{API}/projects/{key}/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _user_token(client: httpx.AsyncClient, owner: str, name: str, roles: list[str]) -> str:
    from tests.support import make_member

    return (await make_member(client, owner, "DEMO", name, roles))[1]


async def test_sprint_lifecycle_items_start_close_gate(server, owner_token: str) -> None:
    client, settings, _app = server
    await _project(client, owner_token)
    task = await _item(client, owner_token, {"kind": "task", "title": "t", "task_type": "qa"})

    # create
    r = await client.post(
        f"{API}/projects/DEMO/sprints",
        json={"name": "Sprint 1", "goal_md": "交付登录"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    sprint = r.json()["data"]
    assert sprint["status"] == "PLANNED"
    sid = sprint["id"]

    # add items
    r = await client.post(
        f"{API}/sprints/{sid}/items",
        json={"items": [task["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    # adding twice -> validation error (unique sprint_item)
    r = await client.post(
        f"{API}/sprints/{sid}/items",
        json={"items": [task["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    # overview shows the item and status counts
    r = await client.get(f"{API}/sprints/{sid}", headers=auth(owner_token))
    assert r.status_code == 200
    body = r.json()["data"]
    assert [i["display_id"] for i in body["items"]] == [task["display_id"]]
    assert body["status_counts"] == {"TODO": 1}

    # start
    r = await client.post(f"{API}/sprints/{sid}/start", headers=auth(owner_token))
    assert r.status_code == 200 and r.json()["data"]["status"] == "ACTIVE"

    # close blocked by the nonterminal task (gate)
    r = await client.post(f"{API}/sprints/{sid}/close", headers=auth(owner_token))
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    assert details["blocking_children"] == [task["display_id"]]
    assert details["target"] == "CLOSED"

    # drive task to DONE -> close passes
    version = 0
    for state in ["IN_PROGRESS", "TO_REVIEW", "DONE"]:
        r = await client.post(
            f"{API}/work-items/{task['display_id']}/transition",
            json={"to": state, "row_version": version},
            headers=auth(owner_token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.post(f"{API}/sprints/{sid}/close", headers=auth(owner_token))
    assert r.status_code == 200 and r.json()["data"]["status"] == "CLOSED"

    # events
    with sqlite3.connect(settings.db_path) as conn:
        types = {
            row[0]
            for row in conn.execute(
                "select distinct event_type from event where aggregate_type='sprint'"
            )
        }
    assert {
        "sprint.created",
        "sprint.item_added",
        "sprint.started",
        "sprint.closed",
    } <= types


async def test_only_one_active_sprint(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    ids = []
    for name in ("S1", "S2"):
        r = await client.post(
            f"{API}/projects/DEMO/sprints",
            json={"name": name},
            headers=auth(owner_token),
        )
        ids.append(r.json()["data"]["id"])

    r = await client.post(f"{API}/sprints/{ids[0]}/start", headers=auth(owner_token))
    assert r.status_code == 200
    r = await client.post(f"{API}/sprints/{ids[1]}/start", headers=auth(owner_token))
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "SPRINT_ACTIVE_EXISTS"
    assert err["details"]["active_sprint_name"] == "S1"

    # closing S1 then starting S2 works
    r = await client.post(f"{API}/sprints/{ids[0]}/close", headers=auth(owner_token))
    assert r.status_code == 200
    r = await client.post(f"{API}/sprints/{ids[1]}/start", headers=auth(owner_token))
    assert r.status_code == 200


async def test_item_can_belong_to_only_one_sprint(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    task = await _item(client, owner_token, {"kind": "task", "title": "t", "task_type": "qa"})
    sids = []
    for name in ("S1", "S2"):
        r = await client.post(
            f"{API}/projects/DEMO/sprints",
            json={"name": name},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        sids.append(r.json()["data"]["id"])

    r = await client.post(
        f"{API}/sprints/{sids[0]}/items",
        json={"items": [task["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    # same item into a different planned sprint -> rejected, naming S1
    r = await client.post(
        f"{API}/sprints/{sids[1]}/items",
        json={"items": [task["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["sprint_id"] == sids[0]
    assert "S1" in err["message"]

    # S2 overview stays empty
    r = await client.get(f"{API}/sprints/{sids[1]}", headers=auth(owner_token))
    assert r.json()["data"]["items"] == []


async def test_cannot_add_items_to_closed_sprint(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    done = await _item(client, owner_token, {"kind": "task", "title": "done", "task_type": "qa"})
    fresh = await _item(client, owner_token, {"kind": "task", "title": "fresh", "task_type": "qa"})
    r = await client.post(
        f"{API}/projects/DEMO/sprints",
        json={"name": "S"},
        headers=auth(owner_token),
    )
    sid = r.json()["data"]["id"]
    r = await client.post(
        f"{API}/sprints/{sid}/items",
        json={"items": [done["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    version = 0
    for state in ["IN_PROGRESS", "TO_REVIEW", "DONE"]:
        r = await client.post(
            f"{API}/work-items/{done['display_id']}/transition",
            json={"to": state, "row_version": version},
            headers=auth(owner_token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.post(f"{API}/sprints/{sid}/start", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    r = await client.post(f"{API}/sprints/{sid}/close", headers=auth(owner_token))
    assert r.status_code == 200, r.text

    r = await client.post(
        f"{API}/sprints/{sid}/items",
        json={"items": [fresh["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["status"] == "CLOSED"


async def test_worker_cannot_create_sprint(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    worker = await _user_token(client, owner_token, "dev", ["worker"])
    r = await client.post(
        f"{API}/projects/DEMO/sprints",
        json={"name": "x"},
        headers=auth(worker),
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_epic_cannot_enter_sprint(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    epic = await _item(client, owner_token, {"kind": "epic", "title": "e"})
    r = await client.post(
        f"{API}/projects/DEMO/sprints",
        json={"name": "S"},
        headers=auth(owner_token),
    )
    sid = r.json()["data"]["id"]
    r = await client.post(
        f"{API}/sprints/{sid}/items",
        json={"items": [epic["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"]["kind"] == "epic"


async def test_backlog_filter_excludes_sprint_items_and_terminal(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    picked = await _item(client, owner_token, {"kind": "story", "title": "in sprint"})
    free = await _item(client, owner_token, {"kind": "story", "title": "free"})
    done = await _item(client, owner_token, {"kind": "task", "title": "done", "task_type": "qa"})

    detail = (
        await client.get(f"{API}/work-items/{done['display_id']}", headers=auth(owner_token))
    ).json()
    await client.post(
        f"{API}/work-items/{done['display_id']}/transition",
        json={
            "to": "CANCELLED",
            "row_version": detail["data"]["row_version"],
        },
        headers=auth(owner_token),
    )

    sprint = (
        await client.post(
            f"{API}/projects/DEMO/sprints",
            json={"name": "S"},
            headers=auth(owner_token),
        )
    ).json()["data"]
    r = await client.post(
        f"{API}/sprints/{sprint['id']}/items",
        json={"items": [picked["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.get(
        f"{API}/projects/DEMO/work-items",
        params={"backlog": "true", "limit": 100},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    ids = {item["display_id"] for item in r.json()["data"]}
    assert free["display_id"] in ids
    assert picked["display_id"] not in ids
    assert done["display_id"] not in ids
