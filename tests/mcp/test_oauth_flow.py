"""M3.2: native OAuth 2.1 authorization-code flow for MCP clients.

Drives the full protocol with httpx (PKCE, DCR, browser consent through the
JSON decision API, token exchange, refresh rotation/reuse, revocation) and
then uses the access token against /mcp like a real MCP client.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport
from mcp.shared.exceptions import MCPError


def _verifier_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _bearer_factory(app, token: str) -> Callable[..., httpx.AsyncClient]:
    def _factory(headers: dict[str, str], **_ignored: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={**headers, "Authorization": f"Bearer {token}"},
        )

    return _factory


async def _ensure_owner_password(client: httpx.AsyncClient) -> None:
    from tests.conftest import OWNER_PASSWORD

    r = await client.post("/api/v1/local/owner-recovery")
    ticket = _query(r.json()["data"]["set_password_url"])["ticket"]
    r = await client.post(
        "/api/v1/auth/set-password",
        json={"ticket": ticket, "new_password": OWNER_PASSWORD},
    )
    assert r.status_code == 200, r.text


async def test_metadata_discovery(server) -> None:
    client, _settings, _app = server
    r = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200, r.text
    resource = r.json()
    assert resource["resource"].rstrip("/").endswith("/mcp")
    assert resource["authorization_servers"]

    r = await client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200, r.text
    metadata = r.json()
    assert "authorization_code" in metadata["grant_types_supported"]
    assert "refresh_token" in metadata["grant_types_supported"]
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["registration_endpoint"].endswith("/register")
    assert metadata["revocation_endpoint"].endswith("/revoke")


async def _register(client, redirect_uri: str = "http://127.0.0.1:54321/callback"):
    r = await client.post(
        "/register",
        json={
            "client_name": "test-mcp-client",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    return r


async def test_dcr_loopback_only(server) -> None:
    client, _settings, _app = server
    r = await _register(client)
    assert r.status_code in (200, 201), r.text
    assert r.json()["client_id"]

    # External / non-loopback redirect URIs are rejected at registration.
    r = await client.post(
        "/register",
        json={"redirect_uris": ["https://example.com/callback"]},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


async def _authorize_to_consent(client, client_id: str) -> tuple[str, str, str, str, str]:
    """Return (consent_id, consent_key, redirect_uri, verifier, state)."""
    from tests.conftest import OWNER_PASSWORD

    redirect_uri = "http://127.0.0.1:54321/callback"
    verifier, challenge = _verifier_pair()
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "mcp",
            "state": "state-xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303, 307), r.text
    location = r.headers["location"]
    assert location.startswith("/login?auth_key="), location
    auth_key = _query(location)["auth_key"]
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "auth_key": auth_key,
            "name": "owner",
            "password": OWNER_PASSWORD,
            "remember": False,
        },
    )
    assert r.status_code == 200, r.text
    location = r.json()["data"]["redirect_to"]
    assert location.startswith("/oauth/consent/"), location
    consent_id = location.split("?")[0].rsplit("/", 1)[1]
    consent_key = _query(location)["key"]
    return consent_id, consent_key, redirect_uri, verifier, "state-xyz"


async def test_authorize_requires_login_then_consent_and_token(server) -> None:
    client, settings, app = server
    registered = (await _register(client)).json()
    client_id = registered["client_id"]

    # Without a session, /authorize bounces to the login page.
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:54321/callback",
            "code_challenge": _verifier_pair()[1],
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"].startswith("/login?auth_key=")

    await _ensure_owner_password(client)

    consent_id, consent_key, redirect_uri, verifier, state = await _authorize_to_consent(
        client, client_id
    )

    # Consent info is reached with the one-shot capability key (§17).
    r = await client.get(f"/api/v1/oauth/consent/{consent_id}?key={consent_key}")
    assert r.status_code == 200, r.text
    info = r.json()["data"]
    assert info["client"]["client_name"] == "test-mcp-client"
    owner = next(u for u in info["selectable_users"] if u["name"] == "owner")

    r = await client.post(
        f"/api/v1/oauth/consent/{consent_id}/decision?key={consent_key}",
        json={"decision": "allow", "act_as_user_id": owner["id"]},
    )
    assert r.status_code == 200, r.text
    redirect_to = r.json()["data"]["redirect_to"]
    q = _query(redirect_to)
    assert q["state"] == state
    code = q["code"]

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if registered.get("client_secret"):
        token_payload["client_secret"] = registered["client_secret"]
    r = await client.post("/token", data=token_payload)
    assert r.status_code == 200, r.text
    tokens = r.json()
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]
    assert tokens["expires_in"] == 3600
    assert tokens["scope"] == "mcp"

    # The OAuth access token authenticates MCP exactly like a PAT.
    transport = StreamableHttpTransport(
        "http://testserver/mcp",
        httpx_client_factory=_bearer_factory(app, access),
    )
    async with Client(transport) as mcp_client:
        tools = await mcp_client.list_tools()
        assert len({t.name for t in tools}) == 28
        result = await mcp_client.call_tool("whoami", {})
        payload = result.structured_content or result.data
        assert payload["data"]["user"]["name"] == "owner"

    return client_id, registered, access, refresh


async def test_refresh_rotation_reuse_and_revocation(server) -> None:
    client, settings, app = server
    (
        client_id,
        registered,
        _access,
        refresh,
    ) = await test_authorize_requires_login_then_consent_and_token(server)

    async def token_request(data: dict) -> httpx.Response:
        data = {**data, "client_id": client_id}
        if registered.get("client_secret"):
            data = {**data, "client_secret": registered["client_secret"]}
        return await client.post("/token", data=data)

    # Rotate: a new pair is issued and the old refresh dies.
    r = await token_request({"grant_type": "refresh_token", "refresh_token": refresh})
    assert r.status_code == 200, r.text
    new_tokens = r.json()
    new_access = new_tokens["access_token"]
    new_refresh = new_tokens["refresh_token"]
    assert new_refresh != refresh

    # Reusing the old refresh token is invalid_grant and revokes the family:
    # even the freshly issued access token stops working. FastMCP's token
    # handler reports invalid_grant with 401.
    r = await token_request({"grant_type": "refresh_token", "refresh_token": refresh})
    assert r.status_code in (400, 401)
    assert r.json()["error"] == "invalid_grant"

    transport = StreamableHttpTransport(
        "http://testserver/mcp", httpx_client_factory=_bearer_factory(app, new_access)
    )
    with pytest.raises(MCPError):
        async with Client(transport) as mcp_client:
            await mcp_client.call_tool("whoami", {})

    # Revocation endpoint exists (client-authenticated) and stays idempotent
    # after the family was already revoked by reuse detection.
    revoke_data: dict = {
        "token": new_refresh,
        "token_type_hint": "refresh_token",
        "client_id": client_id,
    }
    if registered.get("client_secret"):
        revoke_data["client_secret"] = registered["client_secret"]
    r = await client.post("/revoke", data=revoke_data)
    assert r.status_code == 200, r.text


async def test_mcp_token_cannot_call_rest(server) -> None:
    """Scopes separate audiences: an MCP token is not a Web token (§17.79)."""
    client, _settings, _app = server
    (
        _client_id,
        _registered,
        access,
        _refresh,
    ) = await test_authorize_requires_login_then_consent_and_token(server)
    r = await client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401


async def test_web_token_cannot_call_mcp(server) -> None:
    """The mirror case: a browser token must not unlock MCP tools (§17.79)."""
    from tests.conftest import OWNER_PASSWORD, web_login

    client, _settings, app = server
    await _ensure_owner_password(client)
    access, _refresh = await web_login(client, "owner", OWNER_PASSWORD)
    transport = StreamableHttpTransport(
        "http://testserver/mcp", httpx_client_factory=_bearer_factory(app, access)
    )
    with pytest.raises(MCPError):
        async with Client(transport) as mcp_client:
            await mcp_client.list_tools()
