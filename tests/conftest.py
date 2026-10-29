"""Shared fixtures: full HTTP+MCP server app on a tmp data dir (§17)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from rdm.app import create_app
from rdm.config import Settings
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

OWNER_PASSWORD = "OwnerPass123"
WEB_REDIRECT = "http://test/auth/callback"


@pytest_asyncio.fixture
async def server(tmp_path) -> AsyncIterator[tuple[httpx.AsyncClient, Settings, object]]:
    settings = Settings(
        data_dir=tmp_path / "data",
        extra_redirect_uris=WEB_REDIRECT,
    )
    initialize_data_dir(settings.data_dir)
    run_upgrade(settings.data_dir)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, settings, app


async def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


async def web_login(
    client: httpx.AsyncClient, name: str, password: str, *, remember: bool = True
) -> tuple[str, str]:
    """Full first-party OAuth flow; returns (access_token, refresh_token)."""
    verifier, challenge = await pkce()
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "rdm-web",
            "redirect_uri": WEB_REDIRECT,
            "state": "s",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    auth_key = parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]
    r = await client.post(
        "/api/v1/auth/login",
        json={"auth_key": auth_key, "name": name, "password": password, "remember": remember},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["must_reset"] is False, data
    code = parse_qs(urlparse(data["redirect_to"]).query)["code"][0]
    r = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": "rdm-web",
            "redirect_uri": WEB_REDIRECT,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["access_token"], body["refresh_token"]


async def ensure_owner_access(client: httpx.AsyncClient, app) -> str:
    """Set the initial owner password once and return an access token."""
    cached = getattr(app.state, "owner_access", None)
    if cached:
        return cached
    r = await client.post("/api/v1/local/owner-recovery")
    assert r.status_code == 200, r.text
    url = r.json()["data"]["set_password_url"]
    ticket = parse_qs(urlparse(url).query)["ticket"][0]
    r = await client.post(
        "/api/v1/auth/set-password",
        json={"ticket": ticket, "new_password": OWNER_PASSWORD},
    )
    assert r.status_code == 200, r.text
    access, _refresh = await web_login(client, "owner", OWNER_PASSWORD)
    app.state.owner_access = access
    return access


@pytest_asyncio.fixture
async def owner_access(server) -> str:
    client, _settings, app = server
    return await ensure_owner_access(client, app)


@pytest_asyncio.fixture
async def owner_token(server) -> str:
    client, _settings, app = server
    access = await ensure_owner_access(client, app)
    r = await client.post(
        "/api/v1/me/tokens",
        json={"label": "test"},
        headers=auth(access),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
