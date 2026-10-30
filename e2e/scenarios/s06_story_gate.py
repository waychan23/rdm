"""S6: Story TO_TEST→DONE 的 gate：子任务未完成被拒，两路径完成后通过。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect


def _transition(h: Harness, display_id: str, to: str, token_name: str) -> None:
    token = h.tokens[token_name]
    version = _version(h, display_id, token)
    r = h.rest.post(
        f"/work-items/{display_id}/transition",
        {"to": to, "row_version": version},
        token=token,
    )
    assert r.status_code == 200, r.text


def _finish_task(h: Harness, task: dict) -> None:
    tl = h.tokens["tl"]
    display = task["display_id"]
    r = h.rest.post(f"/work-items/{display}/assign", {"member": "tl"}, token=tl)
    assert r.status_code == 200, r.text
    version = _version(h, display, tl)
    status = h.rest.get(f"/work-items/{display}", token=tl).json()["data"]["status"]
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


def run(h: Harness) -> None:
    h.project("S6")
    h.member("S6", "tl", roles=["manager"])
    h.member("S6", "qa", roles=["worker"])
    h.member("S6", "frontend-dev", type_="agent", manager="tl")

    story = h.item("S6", {"kind": "story", "title": "S6 故事", "assignee": "tl"})
    t1 = h.item(
        "S6",
        {
            "kind": "task",
            "title": "S6 前端",
            "task_type": "frontend",
            "parent": story["display_id"],
            "assignee": "frontend-dev",
        },
    )
    t2 = h.item(
        "S6",
        {
            "kind": "task",
            "title": "S6 测试",
            "task_type": "qa",
            "parent": story["display_id"],
            "assignee": "qa",
        },
    )

    # Move story to TO_TEST with open children; DONE must be rejected (gate).
    _transition(h, story["display_id"], "IN_PROGRESS", "tl")
    _transition(h, story["display_id"], "TO_TEST", "tl")
    blocked = h.rest.post(
        f"/work-items/{story['display_id']}/transition",
        {"to": "DONE", "row_version": _version(h, story["display_id"], h.tokens["tl"])},
        token=h.tokens["tl"],
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "WORKFLOW_GATE_BLOCKED"

    # Agents advance their tasks to the review state; DONE is a human step.
    agent_expect(
        h,
        "frontend-dev",
        f"把 {t1['display_id']} 依次转到 IN_PROGRESS、TO_REVIEW，然后停住（不要尝试推 DONE）。",
        lambda out: "TO_REVIEW" in out,
    )
    assert h.db.item(t1["display_id"])["status"] == "TO_REVIEW"
    for to in ("IN_PROGRESS", "TO_REVIEW"):
        _transition(h, t2["display_id"], to, "qa")

    # Manager takes over and performs the review close-out on both tasks.
    _finish_task(h, t1)
    _finish_task(h, t2)
    _transition(h, story["display_id"], "DONE", "tl")
    assert h.db.item(story["display_id"])["status"] == "DONE"


def _version(h: Harness, display_id: str, token: str | None = None) -> int:
    return h.rest.get(f"/work-items/{display_id}", token=token).json()["data"][
        "row_version"
    ]
