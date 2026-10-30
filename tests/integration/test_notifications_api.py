"""Integration: in-app notifications (§17 M7)."""

from __future__ import annotations

import httpx

from tests.support import make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _item(client: httpx.AsyncClient, token: str, title: str) -> dict:
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": title},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_assignment_creates_notification_and_marks_read(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    bob_id, bob_token = await make_member(client, owner_token, "DEMO", "bob", ["worker"])

    item = await _item(client, owner_token, "通知测试")
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": alice_id},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"{API}/notifications", headers=auth(alice_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["unread"] == 1
    row = body["data"][0]
    assert row["type"] == "assignment"
    assert row["entity_ref"] == item["display_id"]
    assert row["url"] == f"/projects/DEMO/items/{item['display_id']}"
    assert row["read_at"] is None

    # Another member does not see somebody else's notification.
    r = await client.get(f"{API}/notifications", headers=auth(bob_token))
    assert r.json()["data"] == []

    # whoami exposes the unread badge.
    r = await client.get(f"{API}/whoami", headers=auth(alice_token))
    assert r.json()["data"]["notification_unread_count"] == 1

    r = await client.post(
        f"{API}/notifications/read",
        json={"ids": [row["id"]]},
        headers=auth(alice_token),
    )
    assert r.status_code == 200 and r.json()["data"]["updated"] == 1
    r = await client.get(f"{API}/notifications?unread_only=true", headers=auth(alice_token))
    assert r.json()["data"] == []
    assert r.json()["meta"]["unread"] == 0

    # read-all is idempotent.
    r = await client.post(f"{API}/notifications/read-all", json={}, headers=auth(alice_token))
    assert r.json()["data"]["updated"] == 0


async def test_notification_prefs_suppress_type(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])

    r = await client.patch(
        f"{API}/me/notification-prefs",
        json={"prefs": {"assignment": False, "step": True}},
        headers=auth(alice_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["prefs"]["assignment"] is False

    item = await _item(client, owner_token, "静默指派")
    await client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": alice_id},
        headers=auth(owner_token),
    )
    r = await client.get(f"{API}/notifications", headers=auth(alice_token))
    assert r.json()["data"] == []

    # Re-enabling restores delivery.
    await client.patch(
        f"{API}/me/notification-prefs",
        json={"prefs": {"assignment": True}},
        headers=auth(alice_token),
    )
    item2 = await _item(client, owner_token, "恢复指派")
    await client.post(
        f"{API}/work-items/{item2['display_id']}/assign",
        json={"member": alice_id},
        headers=auth(owner_token),
    )
    r = await client.get(f"{API}/notifications", headers=auth(alice_token))
    assert len(r.json()["data"]) == 1


async def test_identity_filter_allows_managed_agent(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    r = await client.post(
        f"{API}/me/agents",
        json={"name": "worker-agent"},
        headers=auth(alice_token),
    )
    assert r.status_code == 201, r.text
    agent_id = r.json()["data"]["id"]

    item = await _item(client, owner_token, "agent 指派")
    await client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": agent_id},
        headers=auth(owner_token),
    )

    # The agent gets its own notification; the human can view it via identity.
    r = await client.get(f"{API}/notifications?identity={agent_id}", headers=auth(alice_token))
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["recipient_user_id"] == agent_id
    # Without identity, the human inbox is separate.
    r = await client.get(f"{API}/notifications", headers=auth(alice_token))
    assert r.json()["data"] == []

    # Somebody else cannot read the agent's notifications.
    bob_id, bob_token = await make_member(client, owner_token, "DEMO", "bob", ["worker"])
    r = await client.get(f"{API}/notifications?identity={agent_id}", headers=auth(bob_token))
    assert r.status_code == 404


async def test_step_start_notifies_executors(server, owner_token: str) -> None:
    client, settings, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    rev1_id, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])
    rev2_id, rev2_token = await make_member(client, owner_token, "DEMO", "rev2", ["worker"])

    # Webhook fan-out uses the same executor target set.
    for token in (rev1_token, rev2_token):
        r = await client.patch(
            f"{API}/me",
            json={"notify_webhook": "http://127.0.0.1:1/hook", "notify_webhook_format": "generic"},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text

    item = await _item(client, owner_token, "步骤通知")
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": "dev"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    for to in ("IN_PROGRESS", "TO_REVIEW"):
        r = await client.post(
            f"{API}/work-items/{item['display_id']}/transition",
            json={"to": to, "row_version": version},
            headers=auth(dev_token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={
            "row_version": version,
            "reviewer": ["rev1", "rev2"],
            "review_content_md": "ok",
        },
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/steps/CODE_REVIEW",
        json={"row_version": version, "executors": ["rev1", "rev2"], "note_md": None},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text

    for token in (rev1_token, rev2_token):
        r = await client.get(f"{API}/notifications", headers=auth(token))
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) == 1, rows
        assert rows[0]["type"] == "step"
        assert "待你执行" in rows[0]["title"]
        assert rows[0]["entity_ref"] == item["display_id"]

    # The actor (dev) does not receive a step notification for their own action.
    r = await client.get(f"{API}/notifications", headers=auth(dev_token))
    assert [n for n in r.json()["data"] if n["type"] == "step"] == []

    import json
    import sqlite3

    con = sqlite3.connect(settings.data_dir / "rdm.db")
    try:
        payloads = [
            json.loads(row[0])
            for row in con.execute("select payload from webhook_outbox").fetchall()
        ]
    finally:
        con.close()
    assert {p["event"] for p in payloads} == {"work_item.step_started"}
    assert {p["data"]["display_id"] for p in payloads} == {item["display_id"]}
