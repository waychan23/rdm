"""Authentication (§17): OAuth login tickets, passwords, PAT rules.

No session cookie exists any more; the browser flow is Auth Code + PKCE against
the first-party rdm-web client, and the CLI/MCP use PATs.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, urlparse

from sqlalchemy import update

from rdm.infrastructure.db.models import UserTokenModel
from tests.conftest import OWNER_PASSWORD, ensure_owner_access, web_login
from tests.support import PASSWORD, create_agent, create_human, login_pat


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login_ticket(client) -> str:
    from tests.conftest import pkce

    _verifier, challenge = await pkce()
    r = await client.get(
        "/authorize",
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
        "/token",
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
