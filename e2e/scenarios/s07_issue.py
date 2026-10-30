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
    # The terminal child is review-closed by the assignee through the Code
    # Review step (task has no IN_PROGRESS->DONE edge).
    _finish_task(h, fix)

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


def _finish_task(h: Harness, task: dict) -> None:
    qa = h.tokens["qa"]
    display = task["display_id"]
    version = h.rest.get(f"/work-items/{display}", token=qa).json()["data"]["row_version"]
    for to in ("IN_PROGRESS", "TO_REVIEW"):
        r = h.rest.post(
            f"/work-items/{display}/transition",
            {"to": to, "row_version": version},
            token=qa,
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    r = h.rest.patch(
        f"/work-items/{display}",
        {"row_version": version, "review_content_md": "LGTM"},
        token=qa,
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = h.rest.post(
        f"/work-items/{display}/steps/CODE_REVIEW",
        {"row_version": version},
        token=qa,
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    r = h.rest.post(
        f"/work-item-steps/{active['id']}/execute",
        {"note_md": "reviewed"},
        token=qa,
    )
    assert r.status_code == 200, r.text


def _version(h: Harness, display_id: str) -> int:
    return h.rest.get(f"/work-items/{display_id}", token=h.tokens["qa"]).json()["data"][
        "row_version"
    ]


def _owner_version(h: Harness, display_id: str) -> int:
    return h.rest.get(f"/work-items/{display_id}").json()["data"]["row_version"]
