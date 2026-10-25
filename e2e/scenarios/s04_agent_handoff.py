"""S4: agent 不能把未完成 task 的 story 推 DONE；人类 review 后收口。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect


def run(h: Harness) -> None:
    h.project("S4")
    h.member("S4", "tl", roles=["manager"])
    h.member("S4", "frontend-dev", type_="agent", manager="tl")

    story = h.item("S4", {"kind": "story", "title": "S4 故事"})
    task = h.item(
        "S4",
        {"kind": "task", "title": "S4 前端", "task_type": "frontend",
         "assignee": "frontend-dev"},
    )

    # Worker tries to close the story while the child task is open: must fail.
    result = h.agent(
        "frontend-dev",
        "尝试把 "
        + story["display_id"]
        + " 用 work_item_transition 一路转到 DONE（先 IN_PROGRESS 再 TO_TEST 再 DONE）。"
        "如实报告是否成功以及错误码。",
        timeout=180,
    )
    story_status = h.db.item(story["display_id"])
    assert story_status is not None
    assert story_status["status"] in {"TODO", "IN_PROGRESS", "TO_TEST"}

    # tl completes the child task (review), then closes the story.
    for to in ("IN_PROGRESS", "TO_REVIEW", "DONE"):
        r = h.rest.post(
            f"/work-items/{task['display_id']}/transition",
            {"to": to, "row_version": _version(h, task["display_id"])},
        )
        assert r.status_code == 200, r.text
    agent_expect(
        h,
        "tl",
        f"把 {story['display_id']} 依次转到 IN_PROGRESS、TO_TEST、DONE。",
        lambda out: "DONE" in out,
    )
    assert h.db.item(story["display_id"])["status"] == "DONE"
    assert "GATE_BLOCKED" in result.stdout or "blocking" in result.stdout.lower()
    assert "work_item.status_changed" in h.db.event_types("S4")


def _version(h: Harness, display_id: str) -> int:
    r = h.rest.get(f"/work-items/{display_id}")
    return r.json()["data"]["row_version"]
