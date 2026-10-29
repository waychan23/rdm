"""S1: Owner 建 DEMO、加 human/agent 与 token；CLI whoami 身份正确。"""

from __future__ import annotations

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect


def run(h: Harness) -> None:
    h.project("DEMO")
    for name, roles in (("pm", ["manager"]), ("tl", ["manager"]), ("qa", ["worker"])):
        h.member("DEMO", name, roles=roles)
    h.member("DEMO", "frontend-dev", type_="agent", manager="tl")
    h.member("DEMO", "backend-dev", type_="agent", manager="tl")

    # Each CLI's headless call must see its own member/project context.
    agent_expect(
        h,
        "frontend-dev",
        "调用 whoami，确认你是 frontend-dev、项目是 DEMO。",
        lambda out: "frontend-dev" in out and "DEMO" in out,
    )
    types = {
        r[0]
        for r in h.db.query("select type from users where name in ('frontend-dev','backend-dev')")
    }
    assert types == {"agent"}
