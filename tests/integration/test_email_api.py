"""Integration: SMTP settings and external mailbox recipients (RDM-121/122)."""

from __future__ import annotations

import httpx

from tests.support import make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


def _settings_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "rdm",
        "password": "smtp-secret",
        "from_address": "rdm@example.com",
        "from_name": "RDM",
    }
    payload.update(overrides)
    return payload


async def test_email_settings_permissions_and_password_redaction(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)

    r = await client.get(f"{API}/email-settings", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["enabled"] is False
    assert data["has_password"] is False
    assert "password" not in data and "password_ciphertext" not in data

    r = await client.patch(
        f"{API}/email-settings", json=_settings_payload(), headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    saved = r.json()["data"]
    assert saved["enabled"] is True
    assert saved["has_password"] is True
    assert "password" not in saved

    # Omitted password keeps the existing secret; empty clears it.
    r = await client.patch(
        f"{API}/email-settings",
        json={"from_name": "RDM bot"},
        headers=auth(owner_token),
    )
    assert r.json()["data"]["has_password"] is True
    r = await client.patch(
        f"{API}/email-settings", json={"password": ""}, headers=auth(owner_token)
    )
    assert r.json()["data"]["has_password"] is False

    # Validation: enabled requires sender/host; security and port are bounded.
    for payload in (
        _settings_payload(from_address=None),
        _settings_payload(smtp_host=None),
        _settings_payload(smtp_security="tls"),
        _settings_payload(smtp_port=0),
        _settings_payload(from_address="not-an-email"),
    ):
        r = await client.patch(f"{API}/email-settings", json=payload, headers=auth(owner_token))
        assert r.status_code == 422, payload

    _user_id, worker = await make_member(client, owner_token, "DEMO", "worker")
    r = await client.get(f"{API}/email-settings", headers=auth(worker))
    assert r.status_code == 403
    r = await client.patch(f"{API}/email-settings", json=_settings_payload(), headers=auth(worker))
    assert r.status_code == 403


async def test_external_recipient_uses_smtp_and_is_recorded(
    server, owner_token: str, monkeypatch
) -> None:
    client, _settings, app = server
    await _project(client, owner_token)
    _alice_id, _alice = await make_member(client, owner_token, "DEMO", "alice")
    r = await client.patch(
        f"{API}/email-settings", json=_settings_payload(), headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text

    sent: list[dict] = []

    async def fake_send(settings, *, recipients, subject, text, reply_to=None):
        sent.append(
            {
                "recipients": list(recipients),
                "subject": subject,
                "text": text,
                "reply_to": reply_to,
            }
        )

    monkeypatch.setattr(app.state.container.email_sender, "send", fake_send)

    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={
            "to": ["alice", "client@example.com"],
            "cc": ["cc@example.com", "alice"],
            "subject": "外部通知",
            "body_md": "请查收",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    payload = r.json()["data"]
    assert payload["deliveries"] == 1
    assert payload["external_recipients"] == 2
    assert len(sent) == 1
    assert sent[0]["recipients"] == [
        ("client@example.com", "to"),
        ("cc@example.com", "cc"),
    ]
    assert sent[0]["subject"] == "外部通知"
    assert sent[0]["text"] == "请查收"
    # The sender's own email is used as Reply-To when present.
    assert sent[0]["reply_to"] is None or "@" in sent[0]["reply_to"]

    # Sent view lists internal and external recipients together.
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?folder=sent&unread_only=false",
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    message = r.json()["data"]["messages"][0]
    recipients = {row["id"]: row for row in message["recipients"]}
    assert set(recipients) == {_alice_id, "client@example.com", "cc@example.com"}
    assert recipients["client@example.com"]["type"] == "external"
    assert recipients["client@example.com"]["recipient_type"] == "to"
    assert recipients["cc@example.com"]["recipient_type"] == "cc"
    assert recipients[_alice_id]["name"] == "alice"
    assert recipients[_alice_id]["recipient_type"] == "to"

    # Test endpoint sends through the same configured sender.
    r = await client.post(
        f"{API}/email-settings/test",
        json={"to": "check@example.com"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert sent[-1]["recipients"] == [("check@example.com", "to")]


async def test_external_recipient_without_configuration_fails_and_rolls_back(
    server, owner_token: str
) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    await make_member(client, owner_token, "DEMO", "alice")

    r = await client.post(
        f"{API}/projects/DEMO/messages",
        json={
            "to": ["alice", "client@example.com"],
            "subject": "外部通知",
            "body_md": "请查收",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "EMAIL_SEND_FAILED"

    # Nothing was persisted for either recipient.
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?unread_only=false",
        headers=auth(owner_token),
    )
    assert r.json()["data"]["messages"] == []
    r = await client.get(
        f"{API}/projects/DEMO/mailbox?folder=sent&unread_only=false",
        headers=auth(owner_token),
    )
    assert r.json()["data"]["messages"] == []
