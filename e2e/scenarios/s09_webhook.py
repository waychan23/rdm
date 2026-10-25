"""S9: webhook HMAC 签名送达 + 断线重试。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from e2e.harness.context import Harness
from e2e.harness.mock_webhook import start_mock_webhook
from e2e.scenarios._helpers import agent_expect


def run(h: Harness) -> None:
    hook = start_mock_webhook()
    try:
        h.project("S9")
        h.member("S9", "tl", roles=["manager"])
        h.member("S9", "frontend-dev", type_="agent", manager="tl", webhook=hook.url)

        task = h.item("S9", {"kind": "task", "title": "钩子任务", "task_type": "frontend"})

        def signed_delivery() -> bool:
            return len(hook.received) > 0

        agent_expect(
            h,
            "tl",
            f"用 work_item_assign 把 {task['display_id']} 指派给 frontend-dev。",
            lambda out: "frontend-dev" in out,
        )
        # The production worker polls every 2s.
        h.wait(signed_delivery, "mock 应收到带签名的 webhook", timeout=30)
        call = hook.received[0]
        body = call["body"]
        payload = json.loads(body)
        assert call["headers"]["X-RDM-Event"] == "work_item.assigned"
        assert payload["data"]["display_id"] == task["display_id"]

        secret = (h.server.data_dir / "webhook-secret").read_bytes().strip()
        ts = call["headers"]["X-RDM-Timestamp"].encode()
        expected = hmac.new(secret, ts + b"." + body, hashlib.sha256).hexdigest()
        assert call["headers"]["X-RDM-Signature"] == f"sha256={expected}"

        # Disconnect: flip the hook to 500, trigger another event, watch
        # attempts accumulate in the outbox (poll up to ~15s).
        hook.set_fail(99)
        agent_expect(
            h,
            "tl",
            f"把 {task['display_id']} 用 work_item_transition 转到 IN_PROGRESS，"
            "row_version 先 work_item_get 读取。",
            lambda out: "IN_PROGRESS" in out,
        )
        deadline = time.time() + 20
        attempts = 0
        while time.time() < deadline:
            rows = h.db.query("select attempts, status from webhook_outbox order by created_at")
            attempts = max((r["attempts"] for r in rows), default=0)
            if attempts >= 1:
                break
            time.sleep(1)
        assert attempts >= 1, "失败后 outbox 应记录重试次数"
    finally:
        hook.stop()
