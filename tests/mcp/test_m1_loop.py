"""M1 exit-criterion loop through MCP: claim -> transition -> message.

Covers S4 (claim/transition permissions), S5 (mailbox fan-out + cursor),
S8 (illegal transition/delete/restore) using only the 17 M1 tools, as the
real claude/opencode agents will.
"""

from __future__ import annotations

import sqlite3

from tests.mcp.mcp_helpers import call


async def test_m1_single_agent_loop(server, mcp_clients) -> None:
    helpers = mcp_clients
    client, settings, _app = server
    await helpers["create_project"]("DEMO")
    _, backend_token = await helpers["make_member"]("backend", ["worker"], "DEMO")
    _, frontend_token = await helpers["make_member"]("frontend", ["worker"], "DEMO")
    owner = helpers["owner_token"]

    async with (
        helpers["client_for"](backend_token) as backend,
        helpers["client_for"](frontend_token) as frontend,
        helpers["client_for"](owner) as owner_client,
    ):
        # --- context: whoami + workflow ---
        who = await call(frontend, "whoami", {})
        assert who["data"]["identity"]["name"] == "frontend"
        wf = await call(frontend, "workflow_get", {"kind": "task"})
        assert "TO_REVIEW" in wf["data"]["kinds"]["task"]["transitions"]["IN_PROGRESS"]

        # owner creates a story + task for frontend
        story = await call(
            owner_client,
            "work_item_create",
            {"kind": "story", "title": "登录", "project": "DEMO"},
        )
        story_ref = story["data"]["display_id"]
        task = await call(
            owner_client,
            "work_item_create",
            {
                "kind": "task",
                "title": "登录联调",
                "project": "DEMO",
                "parent": story_ref,
                "assignee": "frontend",
                "task_type": "qa",
            },
        )
        task_ref = task["data"]["display_id"]
        assert task["data"]["assignee"]["name"] == "frontend"

        # S4: frontend lists own work and drives it to TO_REVIEW
        mine = await call(frontend, "work_item_list", {"assignee": "me", "project": "DEMO"})
        assert [i["display_id"] for i in mine["data"]] == [task_ref]

        res = await call(
            frontend,
            "work_item_transition",
            {"id": task_ref, "to": "IN_PROGRESS", "row_version": 0},
        )
        assert not res["_is_error"], res
        version = res["data"]["row_version"]
        res = await call(
            frontend,
            "work_item_transition",
            {"id": task_ref, "to": "TO_REVIEW", "row_version": version, "reason": "完成"},
        )
        assert not res["_is_error"], res
        version = res["data"]["row_version"]

        # another worker cannot move it; raw approval transition needs a step
        res = await call(
            backend,
            "work_item_transition",
            {"id": task_ref, "to": "DONE", "row_version": version},
        )
        assert res["_is_error"] and res["error"]["code"] == "WORKFLOW_STEP_REQUIRED"

        # S8: owner cannot skip states even with privilege
        res = await call(
            owner_client,
            "work_item_transition",
            {"id": task_ref, "to": "PUBLISHED", "row_version": version},
        )
        assert res["error"]["code"] == "WORKFLOW_ILLEGAL_TRANSITION"

        # The assignee self-reviews through the named step (human identity).
        res = await call(
            frontend,
            "work_item_update",
            {
                "id": task_ref,
                "row_version": version,
                "review_content_md": "self review",
            },
        )
        assert not res["_is_error"], res
        version = res["data"]["row_version"]
        res = await call(
            frontend,
            "work_item_step",
            {
                "id": task_ref,
                "action": "start",
                "step_key": "CODE_REVIEW",
                "row_version": version,
            },
        )
        assert not res["_is_error"], res
        step_id = res["meta"]["active_step"]["id"]
        res = await call(
            frontend,
            "work_item_step",
            {
                "id": task_ref,
                "action": "execute",
                "step_id": step_id,
                "note_md": "LGTM",
            },
        )
        assert not res["_is_error"], res
        assert res["data"]["status"] == "DONE"
        assert res["meta"]["allowed_transitions"] == ["PUBLISHED"]

        # S5: backend asks frontend to verify the story, referencing the task
        sent = await call(
            backend,
            "mailbox_send",
            {
                "to": ["frontend"],
                "subject": "请验收",
                "body_md": "登录已完成",
                "refs": [story_ref],
                "project": "DEMO",
            },
        )
        assert not sent["_is_error"], sent
        assert sent["data"]["deliveries"] == 1

        inbox = await call(frontend, "mailbox_check", {"project": "DEMO"})
        assert inbox["data"]["unread_count"] == 1
        message = inbox["data"]["messages"][0]
        assert message["subject"] == "请验收"
        assert message["from"]["name"] == "backend"
        assert message["refs"] == [story_ref]
        cursor = inbox["data"]["next_cursor"]
        assert cursor is None  # single page

        # whoami reflects the unread message
        who = await call(frontend, "whoami", {})
        assert who["data"]["unread_count"] == 1

        # incremental fetch after the only delivery is empty
        again = await call(
            frontend, "mailbox_check", {"since": message["delivery_id"], "project": "DEMO"}
        )
        assert again["data"]["messages"] == []

        # S8: comment with mention notifies; cascade delete + restore
        comment = await call(
            backend,
            "comment_add",
            {"work_item_id": task_ref, "body_md": "@frontend 辛苦复测 @ghost"},
        )
        assert comment["meta"]["unresolved_mentions"] == ["ghost"]
        notes = await call(frontend, "mailbox_check", {"project": "DEMO"})
        assert notes["data"]["unread_count"] == 2

        deleted = await call(owner_client, "work_item_delete", {"id": story_ref})
        assert not deleted["_is_error"]
        assert set(deleted["data"]["deleted"]) == {story_ref, task_ref}
        missing = await call(frontend, "work_item_get", {"id": task_ref})
        assert missing["_is_error"] and missing["error"]["code"] == "NOT_FOUND"

        # restoring child first is blocked; root restore revives the batch
        child_first = await call(owner_client, "work_item_restore", {"id": task_ref})
        assert child_first["error"]["code"] == "ALREADY_DELETED"
        restored = await call(owner_client, "work_item_restore", {"id": story_ref})
        assert not restored["_is_error"]
        assert restored["meta"]["restored"] == [story_ref, task_ref]

    # event ledger: every M1 event family used in the loop was recorded once+
    with sqlite3.connect(settings.db_path) as conn:
        types = {row[0] for row in conn.execute("select distinct event_type from event")}
    assert {
        "work_item.created",
        "work_item.status_changed",
        "work_item.deleted",
        "work_item.restored",
        "message.sent",
        "comment.created",
    } <= types
