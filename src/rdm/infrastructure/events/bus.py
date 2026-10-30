"""In-process SSE fan-out (§17 M7).

Single-process only by design: the server is a single uvicorn process with one
SQLite writer. Subscribers are per-user queues; project events are delivered to
subscribers who are members of that project.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamEvent:
    event: str
    data: dict[str, Any]
    id: str | None = None


@dataclass(eq=False)
class _Subscriber:
    user_id: str
    project_ids: set[str]
    queue: asyncio.Queue[StreamEvent] = field(default_factory=asyncio.Queue)


class StreamBus:
    def __init__(self) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: str, project_ids: Iterable[str]) -> _Subscriber:
        subscriber = _Subscriber(user_id=user_id, project_ids=set(project_ids))
        async with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    async def unsubscribe(self, subscriber: _Subscriber) -> None:
        async with self._lock:
            self._subscribers.discard(subscriber)

    def publish_user(self, user_id: str, event: StreamEvent) -> None:
        for subscriber in list(self._subscribers):
            if subscriber.user_id == user_id:
                subscriber.queue.put_nowait(event)

    def publish_project(self, project_id: str, event: StreamEvent) -> None:
        for subscriber in list(self._subscribers):
            if project_id in subscriber.project_ids:
                subscriber.queue.put_nowait(event)

    async def events(self, subscriber: _Subscriber) -> AsyncIterator[StreamEvent]:
        while True:
            yield await subscriber.queue.get()


_BUS = StreamBus()


def get_bus() -> StreamBus:
    return _BUS
