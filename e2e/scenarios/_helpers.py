"""Shared scenario helpers: retried agent prompts and DB predicates."""

from __future__ import annotations

from collections.abc import Callable

from e2e.harness.context import Harness

PREFIX = (
    "你在 rd-manager 系统中工作。只使用 rdm MCP 工具完成任务，不要猜 id，"
    "必要时先用 member_list/work_item_list 查询。完成后用一句话报告结果。\n\n任务："
)


def agent_expect(
    h: Harness,
    member: str,
    task: str,
    check: Callable[[str], bool],
    *,
    tries: int = 2,
    timeout: int = 180,
) -> str:
    """Run an agent prompt up to `tries` times until check(stdout) is true."""
    prompt = PREFIX + task
    last = ""
    for _attempt in range(1, tries + 1):
        result = h.agent(member, prompt, timeout=timeout)
        last = result.stdout
        if check(last):
            return last
    raise AssertionError(f"{member} 未达成预期（{tries} 次尝试）\n输出尾部：{last[-1200:]}")


def item_id(h: Harness, display_id: str) -> str:
    row = h.db.item(display_id)
    assert row is not None, f"{display_id} 不存在"
    return row["id"]


def status_is(h: Harness, display_id: str, status: str) -> Callable[[], bool]:
    def check() -> bool:
        row = h.db.item(display_id)
        return bool(row and row["status"] == status)

    return check
