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


async def test_human_can_read_own_and_agent_mailboxes(server, owner_token: str) -> None:
    """Humans see their own + owned agents' inboxes; identity filter and
    mark-read only cover identities they actually own."""
    from tests.support import create_agent

    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice = await _member(client, owner_token, "alice")
    agent_id = await create_agent(client, alice, "alice-agent")

    for recipient, subject in [("alice", "给人类"), ("alice-agent", "给 agent")]:
        r = await client.post(
            f"{API}/projects/DEMO/messages",
            json={"to": [recipient], "subject": subject, "body_md": "hello"},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text

    # Default (include_agents=false) stays self-only.
    r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(alice))
    assert r.status_code == 200
    assert [m["subject"] for m in r.json()["data"]["messages"]] == ["给人类"]

    # Mixed view returns both, with a clear mailbox owner on every row.
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=false&include_agents=true",
        headers=auth(alice),
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["unread_count"] == 2
    by_subject = {m["subject"]: m for m in body["messages"]}
    assert by_subject["给人类"]["mailbox_owner"] == {
        "id": alice_id,
        "name": "alice",
        "type": "human",
    }
    assert by_subject["给 agent"]["mailbox_owner"]["id"] == agent_id
    assert by_subject["给 agent"]["mailbox_owner"]["type"] == "agent"

    # Identity filter narrows to one mailbox.
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=false&include_agents=true&identity={agent_id}",
        headers=auth(alice),
    )
    assert r.status_code == 200
    assert [m["subject"] for m in r.json()["data"]["messages"]] == ["给 agent"]

    # ...but cannot peek at someone else's mailbox.
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?include_agents=true&identity={owner_token}",
        headers=auth(alice),
    )
    assert r.status_code == 404

    # The human can mark an agent delivery read from the mixed view.
    agent_delivery = by_subject["给 agent"]["delivery_id"]
    r = await client.post(
        f"{API}/messages/read",
        json={"delivery_ids": [agent_delivery]},
        headers=auth(alice),
    )
    assert r.status_code == 200
    assert r.json()["data"]["updated"] == 1
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=true&include_agents=true",
        headers=auth(alice),
    )
    assert r.json()["data"]["unread_count"] == 1
    assert [m["subject"] for m in r.json()["data"]["messages"]] == ["给人类"]


async def test_mailbox_is_project_scoped(server, owner_token: str) -> None:
    from tests.support import add_to_project

    client, _settings, _app = server
    await _project(client, owner_token, "DEMO")
    r = await client.post(
        f"{API}/projects", json={"key": "OTHER", "name": "OTHER"}, headers=auth(owner_token)
    )
    assert r.status_code == 201, r.text
    human_id, human = await _member(client, owner_token, "alice")
    await add_to_project(client, owner_token, "OTHER", human_id, ["worker"])

    for project, subject in [("DEMO", "项目 A 的信"), ("OTHER", "项目 B 的信")]:
        r = await client.post(
            f"{API}/projects/{project}/messages",
            json={"to": ["alice"], "subject": subject, "body_md": "hi"},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text

    r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(human))
    assert [m["subject"] for m in r.json()["data"]["messages"]] == ["项目 A 的信"]
    assert r.json()["data"]["unread_count"] == 1
    demo_delivery = r.json()["data"]["messages"][0]["delivery_id"]

    r = await client.get(f"{API}/projects/OTHER/mailbox?unread_only=false", headers=auth(human))
    assert [m["subject"] for m in r.json()["data"]["messages"]] == ["项目 B 的信"]
    assert r.json()["data"]["unread_count"] == 1

    # Marking read in one project must not touch the other inbox.
    r = await client.post(
        f"{API}/messages/read",
        json={"delivery_ids": [demo_delivery]},
        headers=auth(human),
    )
    assert r.status_code == 200
    assert r.json()["data"]["updated"] == 1
    r = await client.get(f"{API}/projects/DEMO/mailbox", headers=auth(human))
    assert r.json()["data"]["unread_count"] == 0
    r = await client.get(f"{API}/projects/OTHER/mailbox", headers=auth(human))
    assert r.json()["data"]["unread_count"] == 1


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


async def test_archive_sent_search_delete_and_groups(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    _b_id, backend = await _member(client, owner_token, "backend")
    _f_id, frontend = await _member(client, owner_token, "frontend")

    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={"to": ["frontend"], "subject": "预算确认", "body_md": "请确认 Q4 预算"},
        headers=auth(backend),
    )
    assert r.status_code == 201, r.text

    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=false&folder=inbox", headers=auth(frontend)
    )
    row = r.json()["data"]["messages"][0]
    delivery_id = row["delivery_id"]
    assert row["archived_at"] is None

    # Search hits subject/body inside the selected folder.
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=false&q=预算", headers=auth(frontend)
    )
    assert len(r.json()["data"]["messages"]) == 1
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=false&q=不存在", headers=auth(frontend)
    )
    assert r.json()["data"]["messages"] == []

    # Archive moves it out of the inbox into the archived folder.
    r = await client.post(
        f"{API}/messages/archive",
        json={"delivery_ids": [delivery_id], "archived": True},
        headers=auth(frontend),
    )
    assert r.status_code == 200 and r.json()["data"]["updated"] == 1
    r = await client.get(f"{API}/projects/DEMO/mailbox?unread_only=false", headers=auth(frontend))
    assert r.json()["data"]["messages"] == []
    r = await client.get(f"{API}/projects/DEMO/mailbox?folder=archived", headers=auth(frontend))
    assert len(r.json()["data"]["messages"]) == 1
    assert r.json()["data"]["messages"][0]["archived_at"] is not None

    # Sent folder is the sender's own view and lists recipients.
    r = await client.get(f"{API}/projects/DEMO/mailbox?folder=sent", headers=auth(backend))
    sent = r.json()["data"]["messages"]
    assert len(sent) == 1
    assert sent[0]["subject"] == "预算确认"
    assert sent[0]["delivery_id"].startswith("sent:")
    assert sent[0]["recipients"][0]["name"] == "frontend"

    # Group mailboxes are listable after creation.
    r = await client.post(
        f"{API}/projects/DEMO/mailboxes",
        json={"name": "qa-group", "members": ["frontend"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    r = await client.get(f"{API}/projects/DEMO/mailboxes", headers=auth(frontend))
    groups = r.json()["data"]
    assert [g["name"] for g in groups] == ["qa-group"]
    assert [m["name"] for m in groups[0]["members"]] == ["frontend"]

    # Deleting is per-recipient and idempotent.
    r = await client.post(
        f"{API}/messages/delete",
        json={"delivery_ids": [delivery_id]},
        headers=auth(frontend),
    )
    assert r.json()["data"]["deleted"] == 1
    r = await client.get(f"{API}/projects/DEMO/mailbox?folder=archived", headers=auth(frontend))
    assert r.json()["data"]["messages"] == []
    r = await client.post(
        f"{API}/messages/delete",
        json={"delivery_ids": [delivery_id]},
        headers=auth(frontend),
    )
    assert r.json()["data"]["deleted"] == 0


async def test_send_to_group_name_fans_out(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    _a_id, alice = await _member(client, owner_token, "alice")
    _b_id, bob = await _member(client, owner_token, "bob")

    r = await client.post(
        f"{API}/projects/DEMO/mailboxes",
        json={"name": "qa-group", "members": ["alice", "bob"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={"to": ["qa-group"], "subject": "群发通知", "body_md": "请查收"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["deliveries"] == 2

    for token in (alice, bob):
        r = await client.get(f"{API}/projects/DEMO/mailbox", headers=auth(token))
        assert [m["subject"] for m in r.json()["data"]["messages"]] == ["群发通知"]
