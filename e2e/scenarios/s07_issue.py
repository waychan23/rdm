"""S7: Issue 全生命周期 + CLOSED_DONE→REOPEN 往返。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect

PATH = ["TO_CONFIRM", "TO_FIX", "FIXING", "CLOSED_DONE"]
REOPEN_PATH = ["REOPEN", "FIXING", "CLOSED_DONE"]


def run(h: Harness) -> None:
    h.project("S7")
    h.member("S7", "qa", roles=["worker"])

    issue = h.item(
        "S7",
        {
            "kind": "issue",
            "title": "登录失败",
            "severity": "critical",
            "source_story": None,
            "assignee": "qa",
        },
    )
    display = issue["display_id"]

    # CLOSED_DONE gate requires >=1 terminal child (min_children:1).
    fix = h.item(
        "S7",
        {
            "kind": "task",
            "title": "修复任务",
            "task_type": "backend",
            "parent": display,
            "assignee": "qa",
        },
    )
    # The terminal child is review-closed by the privileged owner token;
    # task has no IN_PROGRESS->DONE edge, it passes through TO_REVIEW.
    for to in ("IN_PROGRESS", "TO_REVIEW", "DONE"):
        r = h.rest.post(
            f"/work-items/{fix['display_id']}/transition",
            {"to": to, "row_version": _owner_version(h, fix["display_id"])},
        )
        assert r.status_code == 200, r.text

    for to in PATH:
        r = h.rest.post(
            f"/work-items/{display}/transition",
            {"to": to, "row_version": _version(h, display)},
            token=h.tokens["qa"],
        )
        assert r.status_code == 200, r.text
    assert h.db.item(display)["status"] == "CLOSED_DONE"

    # REOPEN round-trip: agent drives the second cycle.
    agent_expect(
        h,
        "qa",
        f"把 {display} 用 work_item_transition 转到 REOPEN，再转到 FIXING，最后转到 CLOSED_DONE。",
        lambda out: "CLOSED_DONE" in out,
        tries=2,
        timeout=240,
    )
    assert h.db.item(display)["status"] == "CLOSED_DONE"
    types = h.db.event_types("S7")
    assert "work_item.status_changed" in types


def _version(h: Harness, display_id: str) -> int:
    return h.rest.get(f"/work-items/{display_id}", token=h.tokens["qa"]).json()["data"][
        "row_version"
    ]


def _owner_version(h: Harness, display_id: str) -> int:
    return h.rest.get(f"/work-items/{display_id}").json()["data"]["row_version"]
