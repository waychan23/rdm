"""Unit tests: HMAC signing and webhook payload rendering (M2-4)."""

from __future__ import annotations

import hashlib
import hmac
import json

from rdm.application.services.webhook_notify import build_view, render_payload
from rdm.domain.constants import DEFAULT_ORG_ID
from rdm.domain.entities import Project, User
from rdm.infrastructure.webhook.signing import WebhookSecretStore, sign


def test_sign_known_vector() -> None:
    secret = b"secret"
    body = b'{"a":1}'
    ts = 1700000000
    expected = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    assert sign(secret, ts, body) == expected


def test_secret_store_creates_0600_file(tmp_path) -> None:
    path = tmp_path / "webhook-secret"
    store = WebhookSecretStore(path)
    first = store.get()
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    # Second store reads the same secret.
    assert WebhookSecretStore(path).get() == first


def _view(event: str, data: dict) -> dict:
    project = Project(id="p1", org_id=DEFAULT_ORG_ID, key="DEMO", name="DEMO")
    actor = User(id="m1", org_id=DEFAULT_ORG_ID, type="human", name="tl")
    return build_view(logical_event=event, project=project, event_id=7, actor=actor, data=data)


def test_render_generic_is_the_view() -> None:
    view = _view("work_item.assigned", {"display_id": "DEMO-3", "status": "OPEN"})
    out = render_payload("generic", view)
    assert out["event"] == "work_item.assigned"
    assert out["project"] == {"id": "p1", "key": "DEMO"}
    assert out["data"]["display_id"] == "DEMO-3"
    assert out["actor"]["name"] == "tl"
    json.dumps(out, ensure_ascii=False)


def test_render_dingtalk_markdown() -> None:
    long = "x" * 300
    view = _view(
        "mailbox.delivered",
        {"subject": "联调", "from_name": "be", "body_excerpt": long},
    )
    out = render_payload("dingtalk", view)
    assert out["msgtype"] == "markdown"
    title = out["markdown"]["title"]
    assert "联调" in title
    assert "DEMO" in out["markdown"]["text"]
    # Excerpt is capped.
    assert "…" in out["markdown"]["text"]


def test_render_feishu_text() -> None:
    view = _view("sprint.started", {"name": "S24", "status": "ACTIVE"})
    out = render_payload("feishu", view)
    assert out["msg_type"] == "text"
    assert "S24" in out["content"]["text"]
    assert "started" in out["content"]["text"]


def test_render_status_changed_summary() -> None:
    view = _view(
        "work_item.status_changed",
        {"display_id": "DEMO-9", "title": "任务", "status": "IN_PROGRESS", "assignee_name": "fe"},
    )
    dt_out = render_payload("dingtalk", view)
    assert "DEMO-9" in dt_out["markdown"]["text"]
    assert "IN_PROGRESS" in dt_out["markdown"]["text"]
