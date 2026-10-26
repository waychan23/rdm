"""M3 authentication: password login, sessions, password management, PAT rules."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import update

from rdm.infrastructure.db.models.member import MemberTokenModel


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner_password(settings) -> str:
    return settings.bootstrap_password_path.read_text(encoding="utf-8").strip()


async def test_login_success_then_me_and_logout(server, owner_token) -> None:
    client, settings, _app = server
    # No session before login.
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    r = await client.post(
        "/api/v1/auth/login",
        json={
            "project_key": "RDM",
            "name": "owner",
            "password": _owner_password(settings),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["name"] == "owner"
    assert "password_hash" not in body
    assert "rdm_session" in r.headers.get("set-cookie", "")

    # Cookie authenticates subsequent API calls.
    r = await client.get("/api/v1/whoami")
    assert r.status_code == 200
    assert r.json()["data"]["member"]["name"] == "owner"

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_login_wrong_password_uniform_401(server) -> None:
    client, settings, _app = server
    for payload in (
        {"project_key": "RDM", "name": "owner", "password": "definitely-wrong"},
        {"project_key": "RDM", "name": "ghost", "password": "whatever12345"},
        {"project_key": "NOPE", "name": "owner", "password": "whatever12345"},
    ):
        r = await client.post("/api/v1/auth/login", json=payload)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_agent_cannot_login(server, owner_token) -> None:
    client, _settings, _app = server
    # Create a human manager then an agent.
    r = await client.post(
        "/api/v1/projects/RDM/members",
        headers=auth(owner_token),
        json={"name": "tl", "type": "human", "roles": ["manager"]},
    )
    assert r.status_code == 201, r.text
    tl_id = r.json()["data"]["id"]
    r = await client.post(
        "/api/v1/projects/RDM/members",
        headers=auth(owner_token),
        json={"name": "bot", "type": "agent", "manager_member_id": tl_id, "roles": ["worker"]},
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/auth/login",
        json={"project_key": "RDM", "name": "bot", "password": "longenough123"},
    )
    assert r.status_code == 401


async def test_member_created_with_password_can_login(server, owner_token) -> None:
    client, _settings, _app = server
    r = await client.post(
        "/api/v1/projects/RDM/members",
        headers=auth(owner_token),
        json={
            "name": "alice",
            "type": "human",
            "roles": ["worker"],
            "password": "alice-secret-pw",
        },
    )
    assert r.status_code == 201, r.text
    assert "password_hash" not in r.json()["data"]

    # Fresh cookie jar: use a throwaway client.
    import httpx
    from httpx import ASGITransport

    transport = ASGITransport(app=_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as alice:
        r = await alice.post(
            "/api/v1/auth/login",
            json={"project_key": "RDM", "name": "alice", "password": "alice-secret-pw"},
        )
        assert r.status_code == 200, r.text
        assert (await alice.get("/api/v1/auth/me")).json()["data"]["name"] == "alice"


async def test_change_password_requires_old_and_rotates_session(server, owner_token) -> None:
    client, _settings, app = server
    # member bob logs in.
    assert (
        await client.post(
            "/api/v1/projects/RDM/members",
            headers=auth(owner_token),
            json={"name": "bob", "type": "human", "roles": ["worker"], "password": "bob-old-pw-01"},
        )
    ).status_code == 201
    r = await client.post(
        "/api/v1/auth/login",
        json={"project_key": "RDM", "name": "bob", "password": "bob-old-pw-01"},
    )
    assert r.status_code == 200

    # Wrong old password is rejected.
    r = await client.post(
        "/api/v1/auth/password",
        json={"old_password": "nope-nope", "new_password": "bob-new-pw-02"},
    )
    assert r.status_code == 401

    # Correct old password succeeds; existing session is invalidated.
    r = await client.post(
        "/api/v1/auth/password",
        json={"old_password": "bob-old-pw-01", "new_password": "bob-new-pw-02"},
    )
    assert r.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    # Old password no longer works; the new one does.
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"project_key": "RDM", "name": "bob", "password": "bob-old-pw-01"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"project_key": "RDM", "name": "bob", "password": "bob-new-pw-02"},
        )
    ).status_code == 200


async def test_owner_resets_member_password(server, owner_token) -> None:
    client, _settings, _app = server
    r = await client.post(
        "/api/v1/projects/RDM/members",
        headers=auth(owner_token),
        json={"name": "carol", "type": "human", "roles": ["worker"], "password": "carol-old-001"},
    )
    carol_id = r.json()["data"]["id"]

    # Non-owner cannot reset.
    assert (
        await client.post(
            f"/api/v1/members/{carol_id}/password",
            json={"password": "hacked-pw-0000"},
        )
    ).status_code == 401  # no credentials at all on this call (cookie jar empty)

    r = await client.post(
        f"/api/v1/members/{carol_id}/password",
        headers=auth(owner_token),
        json={"password": "carol-new-002"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["password"] == "carol-new-002"

    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"project_key": "RDM", "name": "carol", "password": "carol-old-001"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"project_key": "RDM", "name": "carol", "password": "carol-new-002"},
        )
    ).status_code == 200


async def test_login_throttle_returns_429(server) -> None:
    client, _settings, _app = server
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"project_key": "RDM", "name": "owner", "password": "wrong"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={"project_key": "RDM", "name": "owner", "password": "wrong"},
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


async def test_expired_pat_is_rejected(server, owner_token) -> None:
    client, _settings, app = server
    assert (await client.get("/api/v1/whoami", headers=auth(owner_token))).status_code == 200
    container = app.state.container
    async with container.uow() as uow:
        await uow.session.execute(  # type: ignore[union-attr]
            update(MemberTokenModel)
            .where(MemberTokenModel.kind == "pat")
            .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))
        )
    container.authenticator.invalidate(owner_token)
    r = await client.get("/api/v1/whoami", headers=auth(owner_token))
    assert r.status_code == 401


async def test_owner_cannot_revoke_their_last_pat(server, owner_token) -> None:
    client, _settings, _app = server
    members = (await client.get("/api/v1/projects/RDM/members", headers=auth(owner_token))).json()[
        "data"
    ]
    owner_id = members[0]["id"]
    tokens = (
        await client.get(f"/api/v1/members/{owner_id}/tokens", headers=auth(owner_token))
    ).json()["data"]
    pats = [t for t in tokens if t["kind"] == "pat" and t["is_valid"]]
    assert len(pats) == 1
    r = await client.delete(f"/api/v1/tokens/{pats[0]['id']}", headers=auth(owner_token))
    assert r.status_code == 403
    # The token still works.
    assert (await client.get("/api/v1/whoami", headers=auth(owner_token))).status_code == 200


async def test_session_token_not_accepted_as_bearer_on_mcp(server) -> None:
    # /mcp must not accept a web session as a Bearer credential; the MCP
    # guard allows only pat/oauth_access kinds (M3.2 adds oauth_access).
    client, settings, _app = server
    r = await client.post(
        "/api/v1/auth/login",
        json={"project_key": "RDM", "name": "owner", "password": _owner_password(settings)},
    )
    cookie = r.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    r = await client.post(
        "/mcp",
        headers={**auth(cookie), "Content-Type": "application/json", "Accept": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert r.status_code == 401
