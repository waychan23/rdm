"""Integration: mailbox fan-out, incremental check, comments (plan M1-4, S5)."""

from __future__ import annotations

import httpx

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _member(
    client: httpx.AsyncClient, owner: str, name: str, roles: list[str] | None = None
) -> tuple[str, str]:
    from tests.support import make_member

    return await make_member(client, owner, "DEMO", name, roles or ["worker"])


async def _item(client: httpx.AsyncClient, token: str, payload: dict) -> dict:
    r = await client.post(f"{API}/projects/DEMO/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_send_check_cursor_read_reply(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    task = await _item(
        client, owner_token, {"kind": "task", "title": "登录联调", "task_type": "qa"}
    )
    _be_id, backend = await _member(client, owner_token, "backend")
    _fe_id, frontend = await _member(client, owner_token, "frontend")

    # backend -> frontend, referencing the task
    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={
            "to": ["frontend"],
            "subject": "联调开始",
            "body_md": "请验证登录",
            "refs": [task["display_id"]],
        },
        headers=auth(backend),
    )
    assert r.status_code == 201, r.text
    message_id = r.json()["data"]["message_id"]
    assert r.json()["data"]["deliveries"] == 1

    # frontend default check: unread only
    r = await client.get(f"{API}/projects/DEMO/mailbox", headers=auth(frontend))
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["unread_count"] == 1
    assert body["next_cursor"] is None
    msg = body["messages"][0]
    assert msg["subject"] == "联调开始"
    assert msg["from"]["name"] == "backend"
    assert msg["refs"] == [task["display_id"]]
    assert msg["read_at"] is None
    delivery_id = msg["delivery_id"]

    # incremental: everything after this delivery is empty
    r = await client.get(f"{API}/projects/DEMO/mailbox?since={delivery_id}", headers=auth(frontend))
    assert r.json()["data"]["messages"] == []

    # mark read -> unread inbox empty, but visible with unread_only=false
    r = await client.post(
        f"{API}/messages/read",
        json={"delivery_ids": [delivery_id]},
        headers=auth(frontend),
    )
    assert r.status_code == 200 and r.json()["data"]["updated"] == 1
    r = await client.get(f"{API}/projects/DEMO/mailbox", headers=auth(frontend))
    assert r.json()["data"]["messages"] == []
    r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(frontend))
    assert len(r.json()["data"]["messages"]) == 1

    # reply keeps the thread
    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={
            "to": ["backend"],
            "subject": "Re: 联调",
            "body_md": "收到",
            "reply_to": message_id,
        },
        headers=auth(frontend),
    )
    assert r.status_code == 201, r.text
    r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(backend))
    assert r.json()["data"]["messages"][0]["reply_to_id"] == message_id

    # unknown recipient -> NOT_FOUND
    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={"to": ["ghost"], "subject": "x", "body_md": "y"},
        headers=auth(backend),
    )
    assert r.status_code == 404


async def test_group_mailbox_fanout_to_and_cc(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    _, backend = await _member(client, owner_token, "backend")
    _, frontend = await _member(client, owner_token, "frontend")
    _, qa = await _member(client, owner_token, "qa")

    r = await client.post(
        f"{API}/projects/DEMO/mailboxes",
        json={"name": "dev-team", "members": ["backend", "frontend"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    # qa sends to the group and cc backend (dedup: backend stays 'to')
    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={
            "to": ["dev-team"],
            "cc": ["backend", "qa"],
            "subject": "站会",
            "body_md": "十分钟后",
        },
        headers=auth(qa),
    )
    assert r.status_code == 201
    assert r.json()["data"]["deliveries"] == 3  # backend, frontend, qa

    for token in (backend, frontend, qa):
        r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(token))
        messages = r.json()["data"]["messages"]
        assert len(messages) == 1 and messages[0]["subject"] == "站会"
    # backend came from the group expansion -> to
    r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(backend))
    assert r.json()["data"]["messages"][0]["recipient_type"] == "to"


async def test_comment_mention_notifies_and_whoami(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    task = await _item(client, owner_token, {"kind": "task", "title": "t"})
    _id, backend = await _member(client, owner_token, "backend")
    _id2, frontend = await _member(client, owner_token, "frontend")

    # assign task to frontend so whoami counts it
    await client.post(
        f"{API}/work-items/{task['display_id']}/assign",
        json={"member": "frontend"},
        headers=auth(owner_token),
    )

    r = await client.post(
        f"{API}/work-items/{task['display_id']}/comments",
        json={"body_md": "@frontend 这个你来看看，@ghost 忽略，记得 @frontend"},
        headers=auth(backend),
    )
    assert r.status_code == 201, r.text
    assert r.json()["meta"]["unresolved_mentions"] == ["ghost"]

    r = await client.get(f"{API}/projects/DEMO/mailbox", headers=auth(frontend))
    messages = r.json()["data"]["messages"]
    assert len(messages) == 1
    assert "DEMO-1" in messages[0]["subject"]
    assert messages[0]["refs"] == ["DEMO-1"]

    # whoami carries unread + open item counts
    r = await client.get(f"{API}/whoami", headers=auth(frontend))
    data = r.json()["data"]
    assert data["unread_count"] == 1
    assert data["my_open_items"] == 1
    assert "org_roles" in data
    assert data["identity"]["name"]

    # comment listed on the item
    r = await client.get(
        f"{API}/work-items/{task['display_id']}/comments", headers=auth(owner_token)
    )
    comments = r.json()["data"]
    assert len(comments) == 1
    assert comments[0]["author"]["name"] == "backend"
