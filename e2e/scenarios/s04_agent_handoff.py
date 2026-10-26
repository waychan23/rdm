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
        + " 用 work_item_transition 转到 DONE（如需可先转 IN_PROGRESS、TO_TEST；"
        "也可以先 work_item_assign 自领）。如实报告每一步是否成功以及错误码。",
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
        f"先 work_item_get 查看 {story['display_id']} 的当前状态与 allowed_transitions，"
        "然后用允许的转换把它转到 DONE（它可能已在 TO_TEST）。",
        lambda out: "DONE" in out,
    )
    assert h.db.item(story["display_id"])["status"] == "DONE"
    assert "GATE_BLOCKED" in result.stdout or "blocking" in result.stdout.lower()
    assert "work_item.status_changed" in h.db.event_types("S4")


def _version(h: Harness, display_id: str) -> int:
    r = h.rest.get(f"/work-items/{display_id}")
    return r.json()["data"]["row_version"]
