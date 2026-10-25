"""HTTP delivery for webhook outbox rows."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from rdm.domain.entities import OutboxRow
from rdm.infrastructure.webhook.signing import WebhookSecretStore, sign


@dataclass(frozen=True)
class SendResult:
    ok: bool
    status: int | None
    error: str | None


class HttpxWebhookSender:
    """One shared client; trust_env=False keeps loopback traffic off proxies."""

    def __init__(self, secret_store: WebhookSecretStore, *, timeout: float = 5.0) -> None:
        self._secret = secret_store
        self._client = httpx.AsyncClient(trust_env=False, timeout=timeout)

    def build_headers(self, row: OutboxRow, body: bytes, timestamp: int) -> dict[str, str]:
        signature = sign(self._secret.get(), timestamp, body)
        return {
            "Content-Type": "application/json",
            "X-RDM-Event": row.logical_event or "unknown",
            "X-RDM-Timestamp": str(timestamp),
            "X-RDM-Signature": f"sha256={signature}",
            "X-RDM-Delivery": row.id,
        }

    async def post(self, row: OutboxRow) -> SendResult:
        body = json.dumps(row.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = int(time.time())
        headers = self.build_headers(row, body, timestamp)
        try:
            response = await self._client.post(row.target_url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            return SendResult(False, None, str(exc)[:900])
        if 200 <= response.status_code < 300:
            return SendResult(True, response.status_code, None)
        return SendResult(
            False,
            response.status_code,
            f"HTTP {response.status_code}: {response.text[:300]}",
        )

    async def aclose(self) -> None:
        await self._client.aclose()
