"""Integration: named steps, multi-executor approval, notes and task mode."""

from __future__ import annotations

from tests.support import make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _item(client, token: str, payload: dict, key: str = "DEMO") -> dict:
    r = await client.post(f"{API}/projects/{key}/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _detail(client, token: str, ref: str) -> dict:
    r = await client.get(f"{API}/work-items/{ref}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def _move(
    client,
    token: str,
    ref: str,
    to: str,
    version: int,
    reason: str | None = None,
) -> dict:
    r = await client.post(
        f"{API}/work-items/{ref}/transition",
        json={"to": to, "row_version": version, "reason": reason},
        headers=auth(token),
    )
    return r


async def _to_review(client, token: str, task: dict, *, review_content: str = "ok") -> dict:
    version = task["row_version"]
    for to in ("IN_PROGRESS", "TO_REVIEW"):
        r = await _move(client, token, task["display_id"], to, version)
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": version, "review_content_md": review_content},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _start_step(
    client,
    token: str,
    task: dict,
    key: str,
    *,
    executors: list[str] | None = None,
    note: str | None = None,
) -> dict:
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/steps/{key}",
        json={
            "row_version": task["row_version"],
            "executors": executors,
            "note_md": note,
        },
        headers=auth(token),
    )
    return r


async def test_direct_step_requires_assigned_executor(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    task = await _item(client, owner_token, {"kind": "task", "title": "t", "assignee": "dev"})

    # Owner/manager cannot execute the assignee-only step.
    r = await _move(client, owner_token, task["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKFLOW_STEP_FORBIDDEN"

    r = await _move(client, dev_token, task["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 200, r.text
    moved = r.json()["data"]
    assert moved["status"] == "IN_PROGRESS"

    detail = await _detail(client, dev_token, task["display_id"])
    steps = {s["key"]: s for s in detail["meta"]["available_steps"]}
    assert steps["SUBMIT_REVIEW"]["mode"] == "direct"
    assert steps["SUBMIT_REVIEW"]["can_execute"] is True
    assert detail["meta"]["active_step"] is None


async def test_approval_multi_executor_and_notes(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _rev1, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])
    rev2_id, rev2_token = await make_member(client, owner_token, "DEMO", "rev2", ["worker"])

    task = await _item(client, owner_token, {"kind": "task", "title": "review", "assignee": "dev"})
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1", "rev2"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]

    detail = await _detail(client, dev_token, task["display_id"])
    review = next(s for s in detail["meta"]["available_steps"] if s["key"] == "CODE_REVIEW")
    assert review["mode"] == "approval"
    assert review["note"] == "required"
    assert review["actor_sources"] == ["assignee", "reviewers"]
    assert {c["name"] for c in review["candidates"]} == {"dev", "rev1", "rev2"}
    assert review["can_start"] is True

    r = await _start_step(client, dev_token, task, "CODE_REVIEW", executors=["rev1", "rev2"])
    assert r.status_code == 200, r.text
    started = r.json()
    active = started["meta"]["active_step"]
    assert active["status"] == "PENDING"
    assert {e["user"]["name"] for e in active["executors"]} == {"rev1", "rev2"}
    assert started["data"]["status"] == "TO_REVIEW"

    # A non-executor (even the assignee) cannot execute.
    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "should fail"},
        headers=auth(dev_token),
    )
    assert r.status_code == 403

    # Note is required.
    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": ""},
        headers=auth(rev1_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "WORKFLOW_STEP_NOTE_REQUIRED"

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "LGTM from rev1"},
        headers=auth(rev1_token),
    )
    assert r.status_code == 200, r.text
    partial = r.json()
    assert partial["data"]["status"] == "TO_REVIEW"
    assert partial["meta"]["active_step"]["executors"][0]["status"] == "DONE"

    # Active steps block raw transitions.
    r = await _move(client, dev_token, task["display_id"], "DONE", partial["data"]["row_version"])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WORKFLOW_STEP_IN_PROGRESS"

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "LGTM from rev2"},
        headers=auth(rev2_token),
    )
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["data"]["status"] == "DONE"
    assert done["meta"]["active_step"] is None

    comments = (
        await client.get(f"{API}/work-items/{task['display_id']}/comments", headers=auth(dev_token))
    ).json()["data"]
    by_body = {c["body_md"]: c for c in comments}
    assert by_body["LGTM from rev1"]["author"]["name"] == "rev1"
    assert by_body["LGTM from rev2"]["author"]["id"] == rev2_id


async def test_manager_cannot_override_but_can_take_over(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _mgr_id, mgr_token = await make_member(client, owner_token, "DEMO", "mgr", ["manager"])

    task = await _item(
        client, owner_token, {"kind": "task", "title": "takeover", "assignee": "dev"}
    )
    r = await _move(client, mgr_token, task["display_id"], "IN_PROGRESS", 0)
    assert r.status_code == 403

    # Manager takes over by changing the assignee first.
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/assign",
        json={"member": "me"},
        headers=auth(mgr_token),
    )
    assert r.status_code == 200, r.text
    taken = r.json()["data"]
    assert taken["assignee"]["name"] == "mgr"

    r = await _move(client, mgr_token, task["display_id"], "IN_PROGRESS", taken["row_version"])
    assert r.status_code == 200, r.text


async def test_reassign_and_cancel_step(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _rev1, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])
    _rev2, rev2_token = await make_member(client, owner_token, "DEMO", "rev2", ["worker"])

    task = await _item(
        client, owner_token, {"kind": "task", "title": "reassign", "assignee": "dev"}
    )
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1", "rev2"]},
        headers=auth(dev_token),
    )
    task = r.json()["data"]
    r = await _start_step(client, dev_token, task, "CODE_REVIEW", executors=["rev1"])
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]

    # Non-assignee cannot reassign/cancel.
    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/reassign",
        json={"row_version": active["row_version"], "executors": ["rev2"]},
        headers=auth(rev1_token),
    )
    assert r.status_code == 403

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/reassign",
        json={"row_version": active["row_version"], "executors": ["rev2"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    assert {e["user"]["name"] for e in active["executors"] if e["status"] == "PENDING"} == {"rev2"}

    # rev1 was reassigned away and can no longer execute.
    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "late"},
        headers=auth(rev1_token),
    )
    assert r.status_code == 403

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "ok"},
        headers=auth(rev2_token),
    )
    assert r.status_code == 200, r.text
    # Reassigned-away executors are CANCELLED for audit and must not block the
    # remaining assignments from completing the step.
    completed = r.json()
    assert completed["data"]["status"] == "DONE"
    assert completed["meta"]["active_step"] is None

    # Cancel a fresh step.
    task2 = await _item(client, owner_token, {"kind": "task", "title": "cancel", "assignee": "dev"})
    task2 = await _to_review(client, dev_token, task2)
    r = await client.patch(
        f"{API}/work-items/{task2['display_id']}",
        json={"row_version": task2["row_version"], "reviewer": ["rev1"]},
        headers=auth(dev_token),
    )
    task2 = r.json()["data"]
    r = await _start_step(client, dev_token, task2, "CODE_REVIEW", executors=["rev1"])
    active2 = r.json()["meta"]["active_step"]
    r = await client.post(
        f"{API}/work-item-steps/{active2['id']}/cancel",
        json={"row_version": active2["row_version"], "reason": "错了"},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    cancelled = r.json()
    assert cancelled["data"]["status"] == "TO_REVIEW"
    assert cancelled["meta"]["active_step"] is None


async def test_task_mode_creates_children_and_auto_advances(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    rev1_id, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])
    rev2_id, rev2_token = await make_member(client, owner_token, "DEMO", "rev2", ["worker"])

    task = await _item(
        client, owner_token, {"kind": "task", "title": "task-mode", "assignee": "dev"}
    )
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1", "rev2"]},
        headers=auth(dev_token),
    )
    task = r.json()["data"]

    r = await _start_step(client, dev_token, task, "CODE_REVIEW_TASKS", executors=["rev1", "rev2"])
    assert r.status_code == 200, r.text
    started = r.json()
    assert started["data"]["status"] == "TO_REVIEW"
    active = started["meta"]["active_step"]
    assert active["mode"] == "task"
    assert all(e["task_id"] for e in active["executors"])

    detail = await _detail(client, dev_token, task["display_id"])
    children = detail["meta"]["children"]
    assert len(children) == 2
    assert {c["task_type"] for c in children} == {"code_review"}
    assert {c["assignee"]["id"] for c in children} == {rev1_id, rev2_id}

    # Each executor completes their own code_review child task.
    async def finish_child(token: str, child: dict) -> None:
        version = child["row_version"]
        for to in ("IN_PROGRESS", "IN_REVIEW"):
            r = await _move(client, token, child["display_id"], to, version)
            assert r.status_code == 200, r.text
            version = r.json()["data"]["row_version"]
        r = await _move(client, token, child["display_id"], "DONE", version, reason="reviewed")
        assert r.status_code == 200, r.text

    by_assignee = {c["assignee"]["id"]: c for c in children}
    await finish_child(rev1_token, by_assignee[rev1_id])
    mid = await _detail(client, dev_token, task["display_id"])
    assert mid["data"]["status"] == "TO_REVIEW"
    statuses = {e["user"]["id"]: e["status"] for e in mid["meta"]["active_step"]["executors"]}
    assert statuses[rev1_id] == "DONE" and statuses[rev2_id] == "PENDING"

    await finish_child(rev2_token, by_assignee[rev2_id])
    final = await _detail(client, dev_token, task["display_id"])
    assert final["data"]["status"] == "DONE"
    assert final["meta"]["active_step"] is None


async def test_task_mode_cancel_cascades_children(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _rev1, _rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])
    _rev2, _rev2_token = await make_member(client, owner_token, "DEMO", "rev2", ["worker"])

    task = await _item(
        client, owner_token, {"kind": "task", "title": "cancel-task", "assignee": "dev"}
    )
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1", "rev2"]},
        headers=auth(dev_token),
    )
    task = r.json()["data"]
    r = await _start_step(client, dev_token, task, "CODE_REVIEW_TASKS", executors=["rev1", "rev2"])
    active = r.json()["meta"]["active_step"]
    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/cancel",
        json={"row_version": active["row_version"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    detail = await _detail(client, dev_token, task["display_id"])
    assert detail["data"]["status"] == "TO_REVIEW"
    assert {c["status"] for c in detail["meta"]["children"]} == {"CANCELLED"}


async def test_step_note_attachment_and_delete_protection(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _rev1, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])

    task = await _item(client, owner_token, {"kind": "task", "title": "attach", "assignee": "dev"})
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1"]},
        headers=auth(dev_token),
    )
    task = r.json()["data"]
    r = await _start_step(client, dev_token, task, "CODE_REVIEW", executors=["rev1"])
    active = r.json()["meta"]["active_step"]

    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("review.txt", b"review-bytes", "text/plain")},
        data={"owner_type": "work_item", "owner_ref": task["display_id"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 201, r.text
    attachment = r.json()["data"]

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "LGTM with attachment", "attachment_ids": [attachment["id"]]},
        headers=auth(rev1_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "DONE"

    comments = (
        await client.get(f"{API}/work-items/{task['display_id']}/comments", headers=auth(dev_token))
    ).json()["data"]
    note = next(c for c in comments if c["body_md"] == "LGTM with attachment")
    assert [a["id"] for a in note["attachments"]] == [attachment["id"]]
    r = await client.get(f"{API}/attachments/{attachment['id']}/download", headers=auth(dev_token))
    assert r.status_code == 200 and r.content == b"review-bytes"

    r = await client.delete(f"{API}/comments/{note['id']}", headers=auth(dev_token))
    assert r.status_code == 403


async def test_blocked_gate_and_retry(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _rev1, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])

    task = await _item(client, owner_token, {"kind": "task", "title": "gate", "assignee": "dev"})
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1"]},
        headers=auth(dev_token),
    )
    task = r.json()["data"]
    r = await _start_step(client, dev_token, task, "CODE_REVIEW", executors=["rev1"])
    active = r.json()["meta"]["active_step"]

    # Clear the gated field while the review is in flight.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "review_content_md": None},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "done"},
        headers=auth(rev1_token),
    )
    assert r.status_code == 200, r.text
    blocked = r.json()
    assert blocked["data"]["status"] == "TO_REVIEW"
    step = blocked["meta"]["active_step"]
    assert step["status"] == "BLOCKED"
    assert [m["key"] for m in step["gate_details"]["missing_fields"]] == ["review_content"]

    # Retry while still missing stays blocked.
    r = await client.post(
        f"{API}/work-item-steps/{step['id']}/retry",
        json={"row_version": step["row_version"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200
    assert r.json()["meta"]["active_step"]["status"] == "BLOCKED"

    # Fill the field, then retry succeeds.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={
            "row_version": r.json()["data"]["row_version"],
            "review_content_md": "LGTM",
        },
        headers=auth(dev_token),
    )
    assert r.status_code == 200
    detail = await _detail(client, dev_token, task["display_id"])
    step = detail["meta"]["active_step"]
    r = await client.post(
        f"{API}/work-item-steps/{step['id']}/retry",
        json={"row_version": step["row_version"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["data"]["status"] == "DONE"
    assert done["meta"]["active_step"] is None


async def test_approval_reject_stops_step_and_notifies_assignee(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    _dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    _rev1_id, rev1_token = await make_member(client, owner_token, "DEMO", "rev1", ["worker"])
    rev2_id, rev2_token = await make_member(client, owner_token, "DEMO", "rev2", ["worker"])

    task = await _item(client, owner_token, {"kind": "task", "title": "reject", "assignee": "dev"})
    task = await _to_review(client, dev_token, task)
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "reviewer": ["rev1", "rev2"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]
    r = await _start_step(client, dev_token, task, "CODE_REVIEW", executors=["rev1", "rev2"])
    assert r.status_code == 200, r.text
    detail = await _detail(client, rev1_token, task["display_id"])
    active = detail["meta"]["active_step"]
    step_id = active["id"]
    assert active["can_reject"] is True

    # Reason is mandatory.
    r = await client.post(
        f"{API}/work-item-steps/{step_id}/reject",
        json={"row_version": active["row_version"], "reason": "  "},
        headers=auth(rev1_token),
    )
    assert r.status_code == 422

    # A non-executor (even assignee) cannot reject.
    r = await client.post(
        f"{API}/work-item-steps/{step_id}/reject",
        json={"row_version": active["row_version"], "reason": "no"},
        headers=auth(dev_token),
    )
    assert r.status_code == 403

    r = await client.post(
        f"{API}/work-item-steps/{step_id}/reject",
        json={"row_version": active["row_version"], "reason": "验收标准不满足"},
        headers=auth(rev1_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"]["status"] == "TO_REVIEW"
    assert body["meta"]["active_step"] is None

    detail = await _detail(client, dev_token, task["display_id"])
    assert detail["data"]["status"] == "TO_REVIEW"
    # The rejected step is terminal and no longer active.
    assert detail["meta"]["active_step"] is None

    # Assignee learns about it; the rejecting executor gets no extra notice.
    r = await client.get(f"{API}/notifications", headers=auth(dev_token))
    titles = [n["title"] for n in r.json()["data"] if n["type"] == "step"]
    assert any("被拒绝" in title for title in titles)
    r = await client.get(f"{API}/notifications", headers=auth(rev1_token))
    assert [n for n in r.json()["data"] if "被拒绝" in n["title"]] == []

    # The second executor was cancelled with the step.
    r = await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(rev2_token))
    assert r.status_code == 200
