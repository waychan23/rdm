"""Background webhook delivery worker (single task, §10/§16.48).

- polls pending & due rows in batches of 10
- claim flips rows to delivering inside the write transaction; a crash
  leaves them delivering and reclaim_delivering() picks them up on restart
- HTTP happens outside the write lock/UoW; results are written back in
  short transactions
- backoff 1m/5m/15m; the 4th failed attempt (first + 3 retries) marks failed
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from rdm.config import Settings
from rdm.domain.entities import OutboxRow
from rdm.domain.errors import EmailSendFailed
from rdm.infrastructure.webhook.sender import HttpxWebhookSender, SendResult
from rdm.infrastructure.webhook.signing import WebhookSecretStore
from rdm.interfaces.http.container import Container

logger = logging.getLogger("rdm.webhook")

BATCH = 10


class WebhookWorker:
    def __init__(
        self,
        container: Container,
        settings: Settings,
        sender: HttpxWebhookSender | None = None,
    ) -> None:
        self._container = container
        self._settings = settings
        self._sender = sender or HttpxWebhookSender(
            WebhookSecretStore(settings.webhook_secret_path),
            timeout=settings.webhook_timeout_seconds,
        )
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="rdm-webhook-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=5)
        except (asyncio.CancelledError, TimeoutError):
            pass
        finally:
            self._task = None
        await self._sender.aclose()

    async def run_once(self) -> int:
        """Process one batch; exposed for tests. Returns rows processed."""
        return await self._tick()

    async def _run(self) -> None:
        async with self._container.uow() as uow:
            assert uow.outboxes is not None
            reclaimed = await uow.outboxes.reclaim_delivering(dt.datetime.now(dt.UTC))
        if reclaimed:
            logger.warning("webhook worker reclaimed %d stale delivering rows", reclaimed)
        while not self._stop.is_set():
            try:
                processed = await self._tick()
            except Exception:  # noqa: BLE001 - worker must never die on a bad batch
                logger.exception("webhook tick failed")
                processed = 0
            delay = self._settings.webhook_poll_seconds if processed == 0 else 0
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(delay, 0.05))
            except TimeoutError:
                pass

    async def _tick(self) -> int:
        now = dt.datetime.now(dt.UTC)
        async with self._container.uow() as uow:
            assert uow.outboxes is not None
            rows = await uow.outboxes.claim_due(now, BATCH)
        if not rows:
            return 0
        for row in rows:
            result = await self._deliver(row)
            await self._record(row.id, result)
        return len(rows)

    async def _deliver(self, row: OutboxRow) -> SendResult:
        if row.channel == "email":
            return await self._send_email(row)
        return await self._sender.post(row)

    async def _send_email(self, row: OutboxRow) -> SendResult:
        """SMTP delivery outside the write lock; config/address errors are final."""
        async with self._container.uow() as uow:
            assert uow.projects is not None
            project = await uow.projects.get(row.project_id)
            settings = (
                await uow.email_settings.get(project.org_id)
                if project is not None and uow.email_settings is not None
                else None
            )
        if (
            settings is None
            or not settings.enabled
            or not settings.smtp_host
            or not settings.from_address
        ):
            return SendResult(False, 400, "email notifications are not configured")
        subject = str(row.payload.get("subject") or "")
        text = str(row.payload.get("text") or "")
        try:
            await self._container.email_sender.send(
                settings,
                recipients=[(row.target_url, "to")],
                subject=subject,
                text=text,
            )
        except EmailSendFailed as exc:
            return SendResult(False, None, str(exc)[:900])
        return SendResult(True, None, None)

    async def _record(self, row_id: str, result: SendResult) -> None:
        now = dt.datetime.now(dt.UTC)
        async with self._container.uow() as uow:
            assert uow.outboxes is not None
            if result.ok:
                await uow.outboxes.mark_delivered(row_id, now)
                return
            attempts = await self._attempts(uow, row_id) + 1
            backoff = self._settings.webhook_backoff_seconds
            error = result.error or "delivery failed"
            if attempts > len(backoff) or result.status in {400, 401, 403, 404, 410}:
                # Retryable transport failures use the backoff ladder; a
                # permanent client error fails immediately.
                await uow.outboxes.mark_failed(row_id, attempts, error, now)
                logger.warning("webhook %s permanently failed: %s", row_id, error)
            else:
                next_at = now + dt.timedelta(seconds=backoff[attempts - 1])
                await uow.outboxes.mark_failure(row_id, attempts, next_at, error, now)
                logger.info(
                    "webhook %s attempt %d failed, retry at %s: %s",
                    row_id,
                    attempts,
                    next_at.isoformat(),
                    error[:120],
                )

    async def _attempts(self, uow, row_id: str) -> int:
        # The claimed row carried its attempt count; re-read to stay honest.
        from rdm.infrastructure.db.models import WebhookOutboxModel

        value = await uow.session.get(WebhookOutboxModel, row_id)
        return int(value.attempts) if value is not None else 0
