"""S3: TL 建 Sprint 加 Story；frontend agent 认领 Task→IN_PROGRESS。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect


def run(h: Harness) -> None:
    h.project("S3")
    h.member("S3", "tl", roles=["manager"])
    h.member("S3", "frontend-dev", type_="agent", manager="tl")

    story = h.item("S3", {"kind": "story", "title": "登录故事"})
    task = h.item(
        "S3",
        {"kind": "task", "title": "前端任务", "task_type": "frontend"},
    )

    agent_expect(
        h,
        "tl",
        f"在 S3 用 sprint_create 建 Sprint「Sprint-S3」，再用 sprint_manage "
        f"add_items 把 {story['display_id']} 加入。",
        lambda out: "Sprint-S3" in out,
    )

    def linked() -> bool:
        return bool(
            h.db.query(
                "select 1 from sprint_item si join sprint s on s.id=si.sprint_id "
                "join project p on p.id=s.project_id "
                "where p.key='S3' and si.deleted_at is null"
            )
        )

    h.wait(linked, "story 应进入 sprint", timeout=60)

    agent_expect(
        h,
        "frontend-dev",
        f"用 work_item_assign 认领 {task['display_id']}（指派给你自己），"
        "然后 work_item_transition 转到 IN_PROGRESS。",
        lambda out: "IN_PROGRESS" in out,
    )
    row = h.db.item(task["display_id"])
    assert row["status"] == "IN_PROGRESS"
    assert row["assignee_user_id"] is not None
    assert "sprint.item_added" in h.db.event_types("S3")
