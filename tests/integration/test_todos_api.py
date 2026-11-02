"""Integration: cross-project todo aggregation (§17 M7)."""

from __future__ import annotations

import datetime as dt

import httpx

from tests.support import make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _item(client: httpx.AsyncClient, token: str, payload: dict) -> dict:
    r = await client.post(f"{API}/projects/DEMO/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_todo_assigned_and_overdue(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    item = await _item(
        client,
        owner_token,
        {
            "kind": "task",
            "title": "逾期任务",
            "assignee": alice_id,
            "planned_end_date": yesterday,
        },
    )
    assert item["planned_end_date"] == yesterday

    r = await client.get(f"{API}/todos", headers=auth(alice_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert [row["display_id"] for row in data["assigned"]] == [item["display_id"]]
    assert data["assigned"][0]["project_key"] == "DEMO"
    assert [row["display_id"] for row in data["overdue"]] == [item["display_id"]]
    assert data["pending_steps"] == []

    r = await client.get(f"{API}/todos?project=DEMO", headers=auth(alice_token))
    assert r.json()["data"]["assigned"][0]["display_id"] == item["display_id"]


async def test_todo_pending_step_and_approval(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    _bob_id, bob_token = await make_member(client, owner_token, "DEMO", "bob", ["worker"])

    item = await _item(
        client, owner_token, {"kind": "task", "title": "审批任务", "assignee": "alice"}
    )
    version = item["row_version"]
    for to in ("IN_PROGRESS", "TO_REVIEW"):
        r = await client.post(
            f"{API}/work-items/{item['display_id']}/transition",
            json={"to": to, "row_version": version},
            headers=auth(alice_token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={
            "row_version": version,
            "reviewer": ["bob"],
            "review_content_md": "ok",
        },
        headers=auth(alice_token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/steps/CODE_REVIEW",
        json={"row_version": version, "executors": ["bob"], "note_md": None},
        headers=auth(alice_token),
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"{API}/todos", headers=auth(bob_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["pending_steps"]) == 1
    assert len(data["approvals"]) == 1
    entry = data["approvals"][0]
    assert entry["step"]["key"] == "CODE_REVIEW"
    assert entry["step"]["mode"] == "approval"
    assert entry["item"]["display_id"] == item["display_id"]
    assert entry["project_key"] == "DEMO"

    # Alice is the assignee but not a step executor: no pending step, only item.
    r = await client.get(f"{API}/todos", headers=auth(alice_token))
    data = r.json()["data"]
    assert data["pending_steps"] == []
    assert [row["display_id"] for row in data["assigned"]] == [item["display_id"]]


async def test_todo_identity_filter_allows_managed_agent(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    r = await client.post(
        f"{API}/me/agents",
        json={"name": "todo-agent"},
        headers=auth(alice_token),
    )
    assert r.status_code == 201, r.text
    agent_id = r.json()["data"]["id"]

    item = await _item(
        client, owner_token, {"kind": "task", "title": "agent 待办", "assignee": agent_id}
    )

    # RDM-96: the managing human can scope the todo bundle to their agent.
    r = await client.get(f"{API}/todos?identity={agent_id}", headers=auth(alice_token))
    assert r.status_code == 200, r.text
    assert [row["display_id"] for row in r.json()["data"]["assigned"]] == [item["display_id"]]
    # Without identity the bundle still aggregates the human and their agents
    # (pre-RDM-96 behavior); identity narrows it to one person.
    r = await client.get(f"{API}/todos", headers=auth(alice_token))
    assert [row["display_id"] for row in r.json()["data"]["assigned"]] == [item["display_id"]]
    r = await client.get(f"{API}/todos?identity={alice_id}", headers=auth(alice_token))
    assert r.json()["data"]["assigned"] == []

    # A different human cannot inspect the agent's to-dos.
    _bob_id, bob_token = await make_member(client, owner_token, "DEMO", "bob", ["worker"])
    r = await client.get(f"{API}/todos?identity={agent_id}", headers=auth(bob_token))
    assert r.status_code == 404
