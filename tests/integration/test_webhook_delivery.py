"""Integration: webhook enqueue, HMAC delivery, formats and retries (M2-4)."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from rdm.app import create_app
from rdm.config import Settings
from rdm.infrastructure.webhook.worker import WebhookWorker
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _MockHandler(BaseHTTPRequestHandler):
    fail_remaining = 0
    response_status = 200
    response_body = b"ok"
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        type(self).received.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if type(self).fail_remaining > 0:
            type(self).fail_remaining -= 1
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"err")
            return
        self.send_response(type(self).response_status)
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def mock_server():
    _MockHandler.received = []
    _MockHandler.fail_remaining = 0
    _MockHandler.response_status = 200
    _MockHandler.response_body = b"ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/hook"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@dataclass
class Web:
    client: httpx.AsyncClient
    token: str
    settings: Settings
    worker: WebhookWorker


@pytest_asyncio.fixture
async def web(tmp_path) -> AsyncIterator[Web]:
    settings = Settings(
        data_dir=tmp_path / "data",
        webhook_backoff="0,0,0",
        webhook_poll_seconds=60,
        extra_redirect_uris="http://test/auth/callback",
    )
    initialize_data_dir(settings.data_dir)
    run_upgrade(settings.data_dir)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            from tests.conftest import auth as _auth
            from tests.conftest import ensure_owner_access

            access = await ensure_owner_access(client, app)
            r = await client.post(
                "/api/v1/me/tokens", json={"label": "webhook"}, headers=_auth(access)
            )
            token = r.json()["data"]["token"]
            worker = WebhookWorker(app.state.container, settings)
            yield Web(client, token, settings, worker)
            await worker.stop()


async def _project(client: httpx.AsyncClient, token: str) -> None:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text


async def _member_with_hook(
    client: httpx.AsyncClient, owner: str, name: str, url: str, fmt: str = "generic"
) -> None:
    from tests.support import add_to_project, create_human, login_pat

    user_id = await create_human(client, owner, name)
    await add_to_project(client, owner, "DEMO", user_id, ["worker"])
    token = await login_pat(client, name)
    r = await client.patch(
        f"{API}/me",
        json={"notify_webhook": url, "notify_webhook_format": fmt},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text


async def _task(client: httpx.AsyncClient, token: str) -> dict:
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "前端任务", "task_type": "frontend"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_assignment_delivers_signed_generic_webhook(web: Web, mock_server) -> None:
    await _project(web.client, web.token)
    await _member_with_hook(web.client, web.token, "fe", mock_server)
    item = await _task(web.client, web.token)
    r = await web.client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": "fe"},
        headers=auth(web.token),
    )
    assert r.status_code == 200, r.text

    assert await web.worker.run_once() == 1
    assert len(_MockHandler.received) == 1
    call = _MockHandler.received[0]
    headers, body = call["headers"], call["body"]
    assert headers["X-RDM-Event"] == "work_item.assigned"
    payload = json.loads(body)
    assert payload["event"] == "work_item.assigned"
    assert payload["data"]["display_id"] == item["display_id"]
    assert payload["data"]["assignee_name"] == "fe"

    secret = web.settings.webhook_secret_path.read_bytes().strip()
    expected = hmac.new(
        secret,
        headers["X-RDM-Timestamp"].encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-RDM-Signature"] == f"sha256={expected}"


async def test_three_formats_and_sprint_broadcast(web: Web, mock_server) -> None:
    await _project(web.client, web.token)
    await _member_with_hook(web.client, web.token, "g", mock_server, "generic")
    await _member_with_hook(web.client, web.token, "d", mock_server, "dingtalk")
    await _member_with_hook(web.client, web.token, "f", mock_server, "feishu")
    r = await web.client.post(
        f"{API}/projects/DEMO/sprints", json={"name": "S1"}, headers=auth(web.token)
    )
    sid = r.json()["data"]["id"]
    assert await web.worker.run_once() == 0  # sprint.created is not whitelisted
    r = await web.client.post(f"{API}/sprints/{sid}/start", headers=auth(web.token))
    assert r.status_code == 200, r.text
    assert await web.worker.run_once() == 3

    bodies = [json.loads(c["body"]) for c in _MockHandler.received]
    assert sum(1 for b in bodies if b.get("event") == "sprint.started") == 1
    assert any(b.get("msgtype") == "markdown" for b in bodies)
    assert any(b.get("msg_type") == "text" for b in bodies)


async def test_message_event_maps_to_mailbox_delivered(web: Web, mock_server) -> None:
    await _project(web.client, web.token)
    await _member_with_hook(web.client, web.token, "fe", mock_server)
    r = await web.client.post(
        f"{API}/projects/DEMO/messages",
        json={"to": ["fe"], "subject": "你好", "body_md": "查收"},
        headers=auth(web.token),
    )
    assert r.status_code == 201, r.text
    assert await web.worker.run_once() == 1
    call = _MockHandler.received[0]
    assert call["headers"]["X-RDM-Event"] == "mailbox.delivered"
    payload = json.loads(call["body"])
    assert payload["event"] == "mailbox.delivered"
    assert payload["data"]["subject"] == "你好"


async def test_feishu_application_error_is_not_delivered(web: Web, mock_server) -> None:
    import sqlite3

    await _project(web.client, web.token)
    await _member_with_hook(web.client, web.token, "fe", mock_server, "feishu")
    item = await _task(web.client, web.token)
    await web.client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": "fe"},
        headers=auth(web.token),
    )
    # Feishu returns HTTP 200 with a non-zero code for invalid payloads.
    _MockHandler.response_body = b'{"code":19002,"msg":"params error"}'
    assert await web.worker.run_once() == 1
    with sqlite3.connect(web.settings.db_path) as conn:
        status, attempts, last_error = conn.execute(
            "select status, attempts, last_error from webhook_outbox"
        ).fetchone()
    assert status == "pending"
    assert attempts == 1
    assert "19002" in last_error

    # A real success response is acknowledged as delivered.
    _MockHandler.response_body = b'{"code":0,"msg":"success"}'
    await web.worker.run_once()
    with sqlite3.connect(web.settings.db_path) as conn:
        status = conn.execute("select status from webhook_outbox").fetchone()[0]
    assert status == "delivered"


async def test_four_failures_then_failed(web: Web, mock_server) -> None:
    import sqlite3

    await _project(web.client, web.token)
    await _member_with_hook(web.client, web.token, "fe", mock_server)
    item = await _task(web.client, web.token)
    await web.client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": "fe"},
        headers=auth(web.token),
    )
    _MockHandler.fail_remaining = 5
    for _ in range(4):
        await web.worker.run_once()

    with sqlite3.connect(web.settings.db_path) as conn:
        status = conn.execute("select status, attempts from webhook_outbox").fetchone()
    assert status == ("failed", 4)
    assert len(_MockHandler.received) == 4


async def test_retry_then_recovery_delivers(web: Web, mock_server) -> None:
    import sqlite3

    await _project(web.client, web.token)
    await _member_with_hook(web.client, web.token, "fe", mock_server)
    item = await _task(web.client, web.token)
    await web.client.post(
        f"{API}/work-items/{item['display_id']}/assign",
        json={"member": "fe"},
        headers=auth(web.token),
    )
    _MockHandler.fail_remaining = 1
    await web.worker.run_once()
    await web.worker.run_once()
    with sqlite3.connect(web.settings.db_path) as conn:
        status = conn.execute("select status, attempts from webhook_outbox").fetchone()
    assert status == ("delivered", 1)
    assert len(_MockHandler.received) == 2
