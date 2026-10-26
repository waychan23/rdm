"""In-memory login failure throttle (architecture §16.55).

Process-local and reset on restart, which is sufficient for the
single-process local deployment. Keys are (client host, project, username).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from rdm.domain.errors import RateLimited

MAX_FAILURES = 5
WINDOW_SECONDS = 300


class LoginThrottler:
    def __init__(self, *, max_failures: int = MAX_FAILURES, window: int = WINDOW_SECONDS) -> None:
        self._max = max_failures
        self._window = window
        self._failures: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)

    def _key(self, host: str | None, project_key: str, name: str) -> tuple[str, str, str]:
        return (host or "-", project_key.strip(), name.strip())

    def check(self, host: str | None, project_key: str, name: str) -> None:
        key = self._key(host, project_key, name)
        now = time.monotonic()
        bucket = self._failures[key]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()
        if len(bucket) >= self._max:
            raise RateLimited(
                f"登录失败次数过多，请 {self._window // 60} 分钟后再试",
                details={"retry_after_seconds": self._window},
            )

    def record_failure(self, host: str | None, project_key: str, name: str) -> None:
        self._failures[self._key(host, project_key, name)].append(time.monotonic())

    def reset(self, host: str | None, project_key: str, name: str) -> None:
        self._failures.pop(self._key(host, project_key, name), None)
