"""Poll helpers: every MCP-driven step is validated by eventual DB state."""

from __future__ import annotations

import time
from collections.abc import Callable


def wait_until[T](
    predicate: Callable[[], T],
    *,
    timeout: float = 120,
    interval: float = 1.0,
    message: str = "condition not met",
) -> T:
    deadline = time.time() + timeout
    last: object = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"{message} (last={last!r})")
