"""S4: agent 不能把未完成 task 的 story 推 DONE；人类 review 后收口。"""

from __future__ import annotations

from e2e.harness.context import Harness


def run(h: Harness) -> None:
    h.project("S4")
    h.member("S4", "tl", roles=["manager"])
    h.member("S4", "frontend-dev", type_="agent", manager="tl")

    story = h.item("S4", {"kind": "story", "title": "S4 故事", "assignee": "tl"})
    task = h.item(
        "S4",
        {
            "kind": "task",
            "title": "S4 前端",
            "task_type": "frontend",
            "parent": story["display_id"],
            "assignee": "frontend-dev",
        },
    )

    # Worker tries to close the story while the child task is open: must fail.
    result = h.agent(
        "frontend-dev",
        "尝试把 "
        + story["display_id"]
        + " 用 work_item_transition 转到 DONE（如需可先 work_item_assign 自领、"
        "再转 IN_PROGRESS/TO_TEST；也可以直接报告权限/步骤错误）。"
        "如实报告每一步是否成功以及错误码。",
        timeout=180,
    )
    story_status = h.db.item(story["display_id"])
    assert story_status is not None
    assert story_status["status"] in {"TODO", "IN_PROGRESS", "TO_TEST"}

    # tl takes the story over if the agent claimed it, then completes the child
    # task through the Code Review step and closes the story.
    h.rest.post(
        f"/work-items/{story['display_id']}/assign",
        {"member": "tl"},
        token=h.tokens["tl"],
    )
    _finish_task(h, task)

    version = _version(h, story["display_id"])
    status = h.rest.get(f"/work-items/{story['display_id']}").json()["data"]["status"]
    if status == "TODO":
        for to in ("IN_PROGRESS", "TO_TEST"):
            r = h.rest.post(
                f"/work-items/{story['display_id']}/transition",
                {"to": to, "row_version": version},
                token=h.tokens["tl"],
            )
            assert r.status_code == 200, r.text
            version = r.json()["data"]["row_version"]
    r = h.rest.post(
        f"/work-items/{story['display_id']}/transition",
        {"to": "DONE", "row_version": version},
        token=h.tokens["tl"],
    )
    assert r.status_code == 200, r.text
    assert h.db.item(story["display_id"])["status"] == "DONE"
    out = result.stdout.lower()
    assert any(token in out for token in ("gate_blocked", "blocking", "workflow_step_forbidden"))
    assert "work_item.status_changed" in h.db.event_types("S4")


def _finish_task(h: Harness, task: dict) -> None:
    tl = h.tokens["tl"]
    display = task["display_id"]
    # Take over from the agent so tl can act as the assignee.
    r = h.rest.post(f"/work-items/{display}/assign", {"member": "tl"}, token=tl)
    assert r.status_code == 200, r.text
    version = _version(h, display)
    status = h.rest.get(f"/work-items/{display}").json()["data"]["status"]
    moves = {
        "TODO": ["IN_PROGRESS", "TO_REVIEW"],
        "IN_PROGRESS": ["TO_REVIEW"],
        "TO_REVIEW": [],
    }.get(status, [])
    for to in moves:
        r = h.rest.post(
            f"/work-items/{display}/transition",
            {"to": to, "row_version": version},
            token=tl,
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = h.rest.patch(
        f"/work-items/{display}",
        {"row_version": version, "review_content_md": "LGTM"},
        token=tl,
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = h.rest.post(
        f"/work-items/{display}/steps/CODE_REVIEW",
        {"row_version": version},
        token=tl,
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    r = h.rest.post(
        f"/work-item-steps/{active['id']}/execute",
        {"note_md": "reviewed"},
        token=tl,
    )
    assert r.status_code == 200, r.text


def _version(h: Harness, display_id: str) -> int:
    r = h.rest.get(f"/work-items/{display_id}")
    return r.json()["data"]["row_version"]
