"""S5: backend→frontend 站内信（refs story）；frontend 查信/已读。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect


def run(h: Harness) -> None:
    h.project("S5")
    h.member("S5", "tl", roles=["manager"])
    h.member("S5", "frontend-dev", type_="agent", manager="tl")
    h.member("S5", "backend-dev", type_="agent", manager="tl")
    story = h.item("S5", {"kind": "story", "title": "S5 联调故事"})

    agent_expect(
        h,
        "backend-dev",
        f"用 mailbox_send 给 frontend-dev 发信，subject「API 就绪」，"
        f"refs 包含 {story['display_id']}，说明登录接口可以联调。",
        lambda out: "deliveries" in out or "1" in out,
    )

    def delivered() -> bool:
        return h.db.scalar(
            "select count(*) from message_delivery d join project_member m "
            "on m.id=d.recipient_member_id join project p on p.id=m.project_id "
            "where p.key='S5' and m.name='frontend-dev'"
        ) >= 1

    h.wait(delivered, "frontend-dev 应有投递", timeout=60)

    agent_expect(
        h,
        "frontend-dev",
        "用 mailbox_check 查看未读信件，找到「API 就绪」后用 mailbox_mark_read 标记已读。",
        lambda out: "API 就绪" in out,
    )
    read = h.db.scalar(
        "select count(*) from message_delivery d join project_member m "
        "on m.id=d.recipient_member_id join project p on p.id=m.project_id "
        "where p.key='S5' and m.name='frontend-dev' and d.read_at is not null"
    )
    assert read >= 1
    assert "message.sent" in h.db.event_types("S5")
