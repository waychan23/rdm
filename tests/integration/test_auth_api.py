"""Authentication (§17): OAuth login tickets, passwords, PAT rules.

No session cookie exists any more; the browser flow is Auth Code + PKCE against
the first-party rdm-web client, and the CLI/MCP use PATs.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, urlparse

from sqlalchemy import update

from rdm.infrastructure.db.models import PasswordTicketModel, UserTokenModel
from tests.conftest import OWNER_PASSWORD, ensure_owner_access, web_login
from tests.support import PASSWORD, create_agent, create_human, login_pat


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login_ticket(client) -> str:
    from tests.conftest import pkce

    _verifier, challenge = await pkce()
    r = await client.get(
        "/api/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "rdm-web",
            "redirect_uri": "http://test/auth/callback",
            "state": "s",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "web",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]


async def test_login_success_then_logout(server) -> None:
    client, _settings, app = server
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    await ensure_owner_access(client, app)
    access, _refresh = await web_login(client, "owner", OWNER_PASSWORD)
    r = await client.get("/api/v1/auth/me", headers=auth(access))
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "owner"
    assert "password_hash" not in r.json()["data"]

    assert (await client.post("/api/v1/auth/logout", headers=auth(access))).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=auth(access))).status_code == 401


async def test_login_wrong_password_uniform_401(server) -> None:
    client, _settings, app = server
    await ensure_owner_access(client, app)
    for name in ("owner", "ghost"):
        auth_key = await _login_ticket(client)
        r = await client.post(
            "/api/v1/auth/login",
            json={"auth_key": auth_key, "name": name, "password": "definitely-wrong"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_public_base_url_resyncs_web_client_on_restart(tmp_path) -> None:
    """RDM_PUBLIC_BASE_URL changes must refresh the first-party redirect whitelist."""
    from asgi_lifespan import LifespanManager

    from rdm.app import create_app
    from rdm.config import Settings
    from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

    data_dir = tmp_path / "data"
    initialize_data_dir(data_dir)
    run_upgrade(data_dir)
    client_row = None
    for origin in ("http://127.0.0.1:5173", "https://rdm.example.com"):
        app = create_app(Settings(data_dir=data_dir, public_base_url=origin))
        async with LifespanManager(app):
            async with app.state.container.uow() as uow:
                client_row = await uow.oauth_clients.get("rdm-web")
        assert client_row is not None
        assert f"{origin}/auth/callback" in client_row.redirect_uris
        # SSH-tunnel access to the loopback bind keeps working.
        assert "http://127.0.0.1:8765/auth/callback" in client_row.redirect_uris


async def test_expired_login_ticket_rejected(server) -> None:
    client, _settings, app = server
    await ensure_owner_access(client, app)
    r = await client.post(
        "/api/v1/auth/login",
        json={"auth_key": "not-a-real-ticket", "name": "owner", "password": OWNER_PASSWORD},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_agent_cannot_login(server, owner_token) -> None:
    client, _settings, _app = server
    await create_human(client, owner_token, "tl")
    tl_token = await login_pat(client, "tl")
    await create_agent(client, tl_token, "bot")

    auth_key = await _login_ticket(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"auth_key": auth_key, "name": "bot", "password": PASSWORD},
    )
    assert r.status_code == 401


async def test_created_user_must_set_password_before_login(server, owner_token) -> None:
    client, _settings, _app = server
    await create_human(client, owner_token, "alice")
    auth_key = await _login_ticket(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"auth_key": auth_key, "name": "alice", "password": "anything-123"},
    )
    # No password yet -> uniform credentials failure (no account enumeration).
    assert r.status_code == 401
    # The reset link works and then the new password logs in.
    alice_token = await login_pat(client, "alice")
    assert (await client.get("/api/v1/whoami", headers=auth(alice_token))).status_code == 200


async def test_change_password_rotates_oauth_but_keeps_pat(server, owner_token) -> None:
    client, _settings, app = server
    await ensure_owner_access(client, app)
    access, refresh = await web_login(client, "owner", OWNER_PASSWORD)
    pats = (await client.get("/api/v1/me/tokens", headers=auth(owner_token))).json()["data"]
    assert pats

    r = await client.post(
        "/api/v1/auth/password",
        headers=auth(access),
        json={"old_password": "nope-nope", "new_password": "OwnerNewPw99"},
    )
    assert r.status_code == 401

    r = await client.post(
        "/api/v1/auth/password",
        headers=auth(access),
        json={"old_password": OWNER_PASSWORD, "new_password": "OwnerNewPw99"},
    )
    assert r.status_code == 200
    # OAuth family is revoked; the PAT survives so automation is not broken.
    assert (await client.get("/api/v1/auth/me", headers=auth(access))).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=auth(owner_token))).status_code == 200
    r = await client.post(
        "/api/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": "rdm-web"},
    )
    assert r.status_code in (400, 401)

    access2, _ = await web_login(client, "owner", "OwnerNewPw99")
    assert (await client.get("/api/v1/auth/me", headers=auth(access2))).status_code == 200


async def test_reset_link_sets_new_password(server, owner_token) -> None:
    client, _settings, _app = server
    user_id = await create_human(client, owner_token, "carol")
    old_token = await login_pat(client, "carol")

    r = await client.post(
        f"/api/v1/users/{user_id}/password-reset-token", headers=auth(owner_token)
    )
    assert r.status_code == 201, r.text
    ticket = parse_qs(urlparse(r.json()["data"]["password_reset_url"]).query)["ticket"][0]
    r = await client.post(
        "/api/v1/auth/set-password", json={"ticket": ticket, "new_password": "CarolNewPw77"}
    )
    assert r.status_code == 200

    # Setting a password revokes every existing credential.
    assert (await client.get("/api/v1/whoami", headers=auth(old_token))).status_code == 401
    new_token = await login_pat(client, "carol", password="CarolNewPw77")
    assert (await client.get("/api/v1/whoami", headers=auth(new_token))).status_code == 200

    # The ticket is one-shot.
    r = await client.post(
        "/api/v1/auth/set-password", json={"ticket": ticket, "new_password": "AnotherPw88"}
    )
    assert r.status_code == 422


async def test_password_ticket_status_is_non_consuming(server, owner_token) -> None:
    """The set-password page evaluates the link on load; checking must not burn it."""
    client, _settings, app = server
    user_id = await create_human(client, owner_token, "dave")

    r = await client.post("/api/v1/auth/password-ticket/check", json={"ticket": "x" * 32})
    assert r.status_code == 200
    assert r.json()["data"] == {
        "valid": False,
        "reason": "not_found",
        "kind": None,
        "expires_at": None,
    }

    r = await client.post(
        f"/api/v1/users/{user_id}/password-reset-token", headers=auth(owner_token)
    )
    assert r.status_code == 201, r.text
    ticket = parse_qs(urlparse(r.json()["data"]["password_reset_url"]).query)["ticket"][0]

    # Repeated checks keep reporting the same valid state.
    for _ in range(2):
        r = await client.post("/api/v1/auth/password-ticket/check", json={"ticket": ticket})
        data = r.json()["data"]
        assert data["valid"] is True
        assert data["reason"] is None
        assert data["kind"] == "reset"

    # Reissuing a link invalidates the previous one; it was never used, so the
    # page must not claim it "was used" (consumed covers both cases).
    r = await client.post(
        f"/api/v1/users/{user_id}/password-reset-token", headers=auth(owner_token)
    )
    newer_ticket = parse_qs(urlparse(r.json()["data"]["password_reset_url"]).query)["ticket"][0]
    r = await client.post("/api/v1/auth/password-ticket/check", json={"ticket": ticket})
    assert r.json()["data"]["valid"] is False
    assert r.json()["data"]["reason"] == "consumed"

    r = await client.post(
        "/api/v1/auth/set-password", json={"ticket": newer_ticket, "new_password": "DaveNewPw77"}
    )
    assert r.status_code == 200
    r = await client.post("/api/v1/auth/password-ticket/check", json={"ticket": newer_ticket})
    assert r.json()["data"]["valid"] is False
    assert r.json()["data"]["reason"] == "consumed"

    # An expired link is reported before the user types a password.
    r = await client.post(
        f"/api/v1/users/{user_id}/password-reset-token", headers=auth(owner_token)
    )
    expired_ticket = parse_qs(urlparse(r.json()["data"]["password_reset_url"]).query)["ticket"][0]
    container = app.state.container
    async with container.uow() as uow:
        await uow.session.execute(  # type: ignore[union-attr]
            update(PasswordTicketModel)
            .where(PasswordTicketModel.consumed_at.is_(None))
            .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))
        )
    r = await client.post("/api/v1/auth/password-ticket/check", json={"ticket": expired_ticket})
    assert r.json()["data"]["valid"] is False
    assert r.json()["data"]["reason"] == "expired"


async def test_login_throttle_returns_429(server) -> None:
    client, _settings, app = server
    await ensure_owner_access(client, app)
    auth_key = await _login_ticket(client)
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"auth_key": auth_key, "name": "owner", "password": "wrong"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={"auth_key": auth_key, "name": "owner", "password": "wrong"},
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


async def test_expired_pat_is_rejected(server, owner_token) -> None:
    client, _settings, app = server
    assert (await client.get("/api/v1/whoami", headers=auth(owner_token))).status_code == 200
    container = app.state.container
    async with container.uow() as uow:
        await uow.session.execute(  # type: ignore[union-attr]
            update(UserTokenModel)
            .where(UserTokenModel.kind == "pat")
            .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))
        )
    container.authenticator.invalidate(owner_token)
    r = await client.get("/api/v1/whoami", headers=auth(owner_token))
    assert r.status_code == 401


async def test_last_pat_can_be_revoked(server, owner_token) -> None:
    """PATs are no longer the only way in (Web OAuth always exists, and the
    owner can recover through the loopback endpoint), so self-lock protection
    for the last PAT was removed (§17)."""
    client, _settings, _app = server
    tokens = (await client.get("/api/v1/me/tokens", headers=auth(owner_token))).json()["data"]
    valid = [t for t in tokens if t["kind"] == "pat" and t["is_valid"]]
    assert len(valid) == 1
    r = await client.delete(f"/api/v1/me/tokens/{valid[0]['id']}", headers=auth(owner_token))
    assert r.status_code == 204
    assert (await client.get("/api/v1/whoami", headers=auth(owner_token))).status_code == 401


async def test_refresh_token_not_accepted_as_bearer(server) -> None:
    client, _settings, app = server
    await ensure_owner_access(client, app)
    _access, refresh = await web_login(client, "owner", OWNER_PASSWORD)
    r = await client.get("/api/v1/whoami", headers=auth(refresh))
    assert r.status_code == 401
