"""Regression: repeated HTTP requests with one OAuth access token.

The Authenticator caches credentials. The cache-hit path used to rebuild a
UserToken without client_id/expires_at, so the *second* authenticated
request made the token look like a PAT (client_id "pat", no expiry). The MCP
streamable manager binds a session to the principal seen at initialize; a
later request with a different client_id was rejected with 404 "Session not
found".

FastMCP's Client multiplexes several JSON-RPC calls over one authenticated
SSE stream (verify_token runs once), so this uses independent HTTP POSTs
exactly like curl / a real client.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
import pytest


def _verifier_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def _ensure_owner_password(client: httpx.AsyncClient) -> None:
    from tests.conftest import OWNER_PASSWORD

    r = await client.post("/api/v1/local/owner-recovery")
    assert r.status_code == 200, r.text
    ticket = parse_qs(urlparse(r.json()["data"]["set_password_url"]).query)["ticket"][0]
    r = await client.post(
        "/api/v1/auth/set-password",
        json={"ticket": ticket, "new_password": OWNER_PASSWORD},
    )
    assert r.status_code == 200, r.text


async def _register(client, redirect_uri: str = "http://127.0.0.1:54321/callback"):
    return await client.post(
        "/register",
        json={
            "client_name": "session-cache-test",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )


async def _oauth_access(client, settings) -> tuple[str, str, str]:
    """Run bootstrap -> DCR -> authorize -> login -> consent -> token."""
    from tests.conftest import OWNER_PASSWORD

    await _ensure_owner_password(client)
    redirect = "http://127.0.0.1:54321/cb"
    registered = (await _register(client, redirect)).json()
    cid, secret = registered["client_id"], registered.get("client_secret")
    verifier, challenge = _verifier_pair()
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect,
            "scope": "mcp",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    auth_key = parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]
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
    consent_url = r.json()["data"]["redirect_to"]
    parsed = urlparse(consent_url)
    consent_id = parsed.path.rsplit("/", 1)[1]
    consent_key = parse_qs(parsed.query)["key"][0]
    info = (await client.get(f"/api/v1/oauth/consent/{consent_id}?key={consent_key}")).json()[
        "data"
    ]
    owner_id = next(u["id"] for u in info["selectable_users"] if u["name"] == "owner")
    decided = (
        await client.post(
            f"/api/v1/oauth/consent/{consent_id}/decision?key={consent_key}",
            json={"decision": "allow", "act_as_user_id": owner_id},
        )
    ).json()["data"]["redirect_to"]
    code = parse_qs(urlparse(decided).query)["code"][0]
    tok = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cid,
            "client_secret": secret,
            "redirect_uri": redirect,
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200, tok.text
    return tok.json()["access_token"], cid, secret


def _sse_json(text: str) -> dict:
    line = next(line for line in text.splitlines() if line.startswith("data:"))
    return json.loads(line[len("data:") :].strip())


@pytest.mark.parametrize("kind_label,header_factory", [("oauth", "oauth")])
async def test_repeated_requests_keep_session(server, kind_label, header_factory):
    client, settings, _app = server
    access, cid, _secret = await _oauth_access(client, settings)
    headers = {
        "Authorization": f"Bearer {access}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def body(method, msg_id, params=None):
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {},
        }

    # 1) initialize — first request, cache miss; server issues a session id
    r = await client.post(
        "/mcp",
        headers=headers,
        json=body(
            "initialize",
            1,
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "curl-like", "version": "1"},
            },
        ),
    )
    assert r.status_code == 200, r.text
    sid = r.headers["mcp-session-id"]
    assert sid
    sess_headers = {**headers, "Mcp-Session-Id": sid}

    # 2) initialized notification — second request, now a cache HIT
    r = await client.post(
        "/mcp",
        headers=sess_headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert r.status_code == 202, r.text

    # 3) tools/list on the same session — must not be rejected as missing session
    r = await client.post("/mcp", headers=sess_headers, json=body("tools/list", 2))
    assert r.status_code == 200, r.text
    assert len(_sse_json(r.text)["result"]["tools"]) == 30


async def test_cached_oauth_token_keeps_client_id_and_expiry(server):
    """Directly assert the cache-hit UserToken preserves OAuth fields."""
    client, settings, _app = server
    access, cid, _secret = await _oauth_access(client, settings)
    from rdm.application.services.tokens import hash_token
    from rdm.domain.enums import BEARER_KINDS

    authenticator = _app.state.container.authenticator
    first = await authenticator.authenticate_with_token(access, allow_kinds=BEARER_KINDS)
    second = await authenticator.authenticate_with_token(access, allow_kinds=BEARER_KINDS)
    assert first.client_id == cid
    assert second.client_id == cid  # cache hits must keep OAuth fields
    assert second.expires_at is not None
    assert second.kind == "oauth_access"
    assert hash_token(access) in authenticator._cache
