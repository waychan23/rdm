"""M2 MCP tools: backlog/my-work, sprint_manage/list/get, member/comment lists,
mailbox_mark_read, artifact_add, attachment_list."""

from __future__ import annotations

import pytest

from tests.mcp.mcp_helpers import call


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _project(rest, owner_token, key="DEMO") -> None:
    r = await rest.post(
        "/api/v1/projects",
        json={"key": key, "name": key},
        headers=_hdr(owner_token),
    )
    assert r.status_code == 201, r.text


async def _make_member(rest, owner_token, name, project="DEMO") -> str:
    from tests.support import make_member

    return (await make_member(rest, owner_token, project, name, ["worker"]))[1]


async def test_backlog_and_my_work_semantics(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as owner_client:
        await _project(rest, mcp_clients["owner_token"])
        story = await call(
            owner_client,
            "work_item_create",
            {"kind": "story", "title": "故事", "project": "DEMO"},
        )
        task = await call(
            owner_client,
            "work_item_create",
            {
                "kind": "task",
                "title": "任务",
                "project": "DEMO",
                "task_type": "qa",
                "assignee": "me",
            },
        )
        story_id = story["data"]["id"]
        story_display = story["data"]["display_id"]

        backlog = await call(owner_client, "backlog_list", {"project": "DEMO"})
        ids = {i["display_id"] for i in backlog["data"]}
        assert story_display in ids and task["data"]["display_id"] in ids

        sprint = await call(owner_client, "sprint_create", {"name": "S1", "project": "DEMO"})
        sid = sprint["data"]["id"]
        managed = await call(
            owner_client,
            "sprint_manage",
            {"id": sid, "action": "add_items", "items": [story_display]},
        )
        assert not managed["_is_error"], managed
        assert managed["meta"]["added"] == [story_display]

        backlog = await call(owner_client, "backlog_list", {"project": "DEMO"})
        ids = {i["display_id"] for i in backlog["data"]}
        assert story_display not in ids
        assert task["data"]["display_id"] in ids

        # work_item_list gains the sprint filter.
        in_sprint = await call(owner_client, "work_item_list", {"sprint": sid, "project": "DEMO"})
        assert [i["id"] for i in in_sprint["data"]] == [story_id]

        got = await call(owner_client, "sprint_get", {"id": sid})
        assert {i["id"] for i in got["data"]["items"]} == {story_id}
        assert sum(got["data"]["status_counts"].values()) == 1

        removed = await call(
            owner_client,
            "sprint_manage",
            {"id": sid, "action": "remove_item", "item": story_display},
        )
        assert removed["meta"]["removed"] == story_display
        backlog = await call(owner_client, "backlog_list", {"project": "DEMO"})
        assert story_display in {i["display_id"] for i in backlog["data"]}

        # Terminal items never appear in the backlog.
        rv = await call(
            owner_client,
            "work_item_list",
            {"q": task["data"]["title"], "project": "DEMO"},
        )
        task_id = rv["data"][0]["id"]
        task_full = await call(owner_client, "work_item_get", {"id": task_id})
        row_version = task_full["data"]["row_version"]
        await call(
            owner_client,
            "work_item_transition",
            {"id": task_id, "to": "CANCELLED", "row_version": row_version},
        )
        backlog = await call(owner_client, "backlog_list", {"project": "DEMO"})
        assert task["data"]["display_id"] not in {i["display_id"] for i in backlog["data"]}

        # my_work_list after assigning the story to a DEMO member.
        dev_token = await _make_member(rest, mcp_clients["owner_token"], "dev")
        await call(
            owner_client,
            "work_item_assign",
            {"id": story_display, "member": "dev"},
        )
        async with mcp_clients["client_for"](dev_token) as dev_client:
            mine = await call(dev_client, "my_work_list", {})
        assert story_display in {i["display_id"] for i in mine["data"]}


async def test_sprint_manage_validation_and_closed_freeze(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as c:
        await _project(rest, mcp_clients["owner_token"])
        sprint = await call(c, "sprint_create", {"name": "S1", "project": "DEMO"})
        sid = sprint["data"]["id"]
        bad = await call(c, "sprint_manage", {"id": sid, "action": "explode"})
        assert bad["_is_error"] and bad["error"]["code"] == "VALIDATION_ERROR"

        await call(c, "sprint_start", {"id": sid})
        await call(c, "sprint_close", {"id": sid})
        story = await call(
            c, "work_item_create", {"kind": "story", "title": "s", "project": "DEMO"}
        )
        rejected = await call(
            c,
            "sprint_manage",
            {"id": sid, "action": "add_items", "items": [story["data"]["display_id"]]},
        )
        assert rejected["_is_error"]
        # CLOSED sprints still allow remove_item/update? update is frozen too;
        # remove_item remains allowed (no items -> NotFound on empty remove).
        renamed = await call(c, "sprint_manage", {"id": sid, "action": "update", "name": "x"})
        assert renamed["_is_error"]

        listed = await call(c, "sprint_list", {"project": "DEMO", "status": "closed"})
        assert [s["id"] for s in listed["data"]] == [sid]


async def test_member_comment_artifact_attachment_tools(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner_token = mcp_clients["owner_token"]
    headers = _hdr(owner_token)
    async with mcp_clients["client_for"](owner_token) as c:
        await _project(rest, owner_token)
        await _make_member(rest, owner_token, "worker1")
        members = await call(c, "member_list", {"project": "DEMO"})
        names = {m["name"] for m in members["data"]}
        assert "worker1" in names
        agents = await call(c, "member_list", {"project": "DEMO", "type": "agent"})
        assert agents["data"] == []

        item = await call(
            c,
            "work_item_create",
            {"kind": "task", "title": "附件任务", "project": "DEMO", "task_type": "backend"},
        )
        display_id = item["data"]["display_id"]

        # artifact_add on item and project
        art = await call(
            c,
            "artifact_add",
            {
                "owner_type": "item",
                "owner": display_id,
                "kind": "design",
                "label": "Figma",
                "url": "https://figma.example/x",
                "project": "DEMO",
            },
        )
        assert not art["_is_error"], art
        bad_url = await call(
            c,
            "artifact_add",
            {
                "owner_type": "project",
                "owner": "DEMO",
                "kind": "link",
                "label": "x",
                "url": "ftp://nope",
                "project": "DEMO",
            },
        )
        assert bad_url["_is_error"]

        # attachment uploaded via REST, listed via MCP
        upload = await rest.post(
            "/api/v1/projects/DEMO/attachments",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            data={"owner_type": "work_item", "owner_ref": display_id},
            headers=headers,
        )
        assert upload.status_code == 201, upload.text
        atts = await call(
            c,
            "attachment_list",
            {"owner": display_id, "owner_type": "work_item", "project": "DEMO"},
        )
        assert not atts["_is_error"]
        assert atts["data"][0]["filename"] == "notes.txt"
        assert atts["data"][0]["download_url"].endswith("/download")

        # comment_add binds the attachment, comment_list surfaces it.
        att_id = atts["data"][0]["id"]
        posted = await call(
            c,
            "comment_add",
            {
                "work_item_id": display_id,
                "body_md": "见附件",
                "attachment_ids": [att_id],
            },
        )
        assert not posted["_is_error"], posted
        comments = await call(c, "comment_list", {"work_item_id": display_id})
        assert comments["data"][0]["attachments"][0]["id"] == att_id


async def test_mailbox_mark_read_tool(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner_token = mcp_clients["owner_token"]
    await _project(rest, owner_token)
    worker_token = await _make_member(rest, owner_token, "reader")
    async with mcp_clients["client_for"](owner_token) as owner_c:
        await call(
            owner_c,
            "mailbox_send",
            {
                "to": ["reader"],
                "subject": "请查收",
                "body_md": "hello",
                "project": "DEMO",
            },
        )
    async with mcp_clients["client_for"](worker_token) as worker_c:
        who = await call(worker_c, "mailbox_check", {"unread_only": True})
        messages = who["data"]["messages"]
        assert messages and messages[0]["delivery_id"]
        result = await call(
            worker_c,
            "mailbox_mark_read",
            {"delivery_ids": [messages[0]["delivery_id"]]},
        )
        assert result["data"]["updated"] == 1
        again = await call(worker_c, "mailbox_check", {"unread_only": True})
        assert again["data"]["messages"] == []


async def test_mailbox_send_reply_chain(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    await _project(rest, owner)
    worker = await _make_member(rest, owner, "replier")

    async with mcp_clients["client_for"](owner) as owner_c:
        sent = await call(
            owner_c,
            "mailbox_send",
            {
                "to": ["replier"],
                "subject": "联调问题",
                "body_md": "这里怎么处理？",
                "project": "DEMO",
            },
        )
        assert not sent["_is_error"], sent
        parent_id = sent["data"]["message_id"]

    async with mcp_clients["client_for"](worker) as worker_c:
        inbox = await call(worker_c, "mailbox_check", {"project": "DEMO"})
        parent = inbox["data"]["messages"][0]
        assert parent["message_id"] == parent_id
        assert parent["reply_to_id"] is None
        reply = await call(
            worker_c,
            "mailbox_send",
            {
                "to": ["owner"],
                "subject": "Re: 联调问题",
                "body_md": "按 A 方案处理。",
                "reply_to": parent_id,
                "project": "DEMO",
            },
        )
        assert not reply["_is_error"], reply
        assert reply["data"]["reply_to_id"] == parent_id
        assert reply["data"]["message_id"] != parent_id

    async with mcp_clients["client_for"](owner) as owner_c:
        inbox = await call(owner_c, "mailbox_check", {"project": "DEMO"})
        replies = [m for m in inbox["data"]["messages"] if m["reply_to_id"] == parent_id]
        assert len(replies) == 1
        assert replies[0]["subject"] == "Re: 联调问题"
        assert replies[0]["from"]["name"] == "replier"


@pytest.mark.parametrize("empty", [[]])
async def test_mailbox_mark_read_requires_ids(server, mcp_clients, empty) -> None:
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as c:
        result = await call(c, "mailbox_mark_read", {"delivery_ids": empty})
        assert result["_is_error"]


async def test_project_inline_images_and_signed_fetch_url(server, mcp_clients) -> None:
    from urllib.parse import urlparse

    rest, _settings, _app = server
    owner_token = mcp_clients["owner_token"]
    await _project(rest, owner_token)
    headers = _hdr(owner_token)

    r = await rest.post(
        "/api/v1/projects/DEMO/work-items",
        json={"kind": "task", "title": "带图任务"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    item = r.json()["data"]

    image = b"\x89PNG\r\n\x1a\nfake"
    r = await rest.post(
        "/api/v1/projects/DEMO/attachments",
        files={"file": ("shot.png", image, "image/png")},
        data={"owner_type": "project", "state": "temp"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    att = r.json()["data"]
    assert att["state"] == "temp"

    r = await rest.patch(
        f"/api/v1/work-items/{item['display_id']}",
        json={
            "row_version": item["row_version"],
            "description_md": f"![shot]({att['download_url']})",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    async with mcp_clients["client_for"](owner_token) as c:
        detail = await call(c, "work_item_get", {"id": item["display_id"]})
        assert not detail["_is_error"], detail
        attachments = detail["meta"]["attachments"]
        assert [a["id"] for a in attachments] == [att["id"]]
        assert attachments[0]["state"] == "active"
        fetch_url = attachments[0]["fetch_url"]
        assert fetch_url.startswith("http://127.0.0.1:8765/api/v1/attachments/")

        listed = await call(
            c,
            "attachment_list",
            {"owner_type": "project", "project": "DEMO"},
        )
        assert not listed["_is_error"], listed
        assert listed["data"][0]["id"] == att["id"]
        assert listed["data"][0]["fetch_url"].startswith("http://")

        parsed = urlparse(fetch_url)
        r = await rest.get(parsed.path + "?" + parsed.query)
        assert r.status_code == 200, r.text
        assert r.content == image

        r = await rest.get(parsed.path + "?exp=9999999999&sig=bad")
        assert r.status_code == 401


async def test_backlog_orders_by_priority(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as owner_client:
        await _project(rest, owner, key="PRI")
        for priority in (4, 1, 3, 2):
            created = await call(
                owner_client,
                "work_item_create",
                {
                    "kind": "task",
                    "title": f"p{priority}",
                    "project": "PRI",
                    "priority": priority,
                    "assignee": "me",
                },
            )
            assert not created["_is_error"], created

        backlog = await call(owner_client, "backlog_list", {"project": "PRI"})
        assert [item["priority"] for item in backlog["data"]] == [1, 2, 3, 4]

        mine = await call(owner_client, "my_work_list", {"project": "PRI"})
        assert [item["priority"] for item in mine["data"]] == [1, 2, 3, 4]
