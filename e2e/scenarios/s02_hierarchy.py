"""S2: PM 建 Epic→Story→Task（含 3 个 Task），parent 结构与事件落库。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect


def run(h: Harness) -> None:
    h.project("S2")
    h.member("S2", "pm", roles=["manager"])

    agent_expect(
        h,
        "pm",
        "在项目 S2 用 work_item_create 创建：1 个 epic「登录 Epic」；"
        "1 个挂在该 epic 下的 story「账号登录」；3 个挂在该 story 下的 task："
        "「前端登录页」「后端鉴权」「测试用例」。",
        lambda out: all(word in out for word in ("S2-", "登录")),
        tries=2,
        timeout=240,
    )

    def hierarchy_ready() -> bool:
        rows = h.db.query(
            "select wi.kind, p.key, wi.title, parent.kind as pk from work_item wi "
            "join project p on p.id=wi.project_id "
            "left join work_item parent on parent.id=wi.parent_id "
            "where p.key='S2'"
        )
        return len(rows) >= 5

    h.wait(hierarchy_ready, "S2 应有 5 个工作项", timeout=180)
    rows = h.db.query(
        "select wi.kind, parent.kind as pk, wi.title from work_item wi "
        "join project p on p.id=wi.project_id "
        "left join work_item parent on parent.id=wi.parent_id where p.key='S2'"
    )
    kinds = {r["kind"] for r in rows}
    assert {"epic", "story", "task"} <= kinds
    story = next(r for r in rows if r["kind"] == "story")
    assert story["pk"] == "epic"
    tasks = [r for r in rows if r["kind"] == "task"]
    assert len(tasks) == 3 and all(r["pk"] == "story" for r in tasks)
    assert "work_item.created" in h.db.event_types("S2")
