"""CLI tests: a real uvicorn server on an ephemeral port (§17 identity)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import uvicorn

from rdm.app import create_app
from rdm.config import Settings
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

OWNER_PASSWORD = "OwnerPass123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _owner_pat(base: str) -> str:
    """Bootstrap the owner password and mint a PAT over the real HTTP API."""
    with httpx.Client(timeout=10, trust_env=False) as client:
        r = client.post(f"{base}/api/v1/local/owner-recovery")
        assert r.status_code == 200, r.text
        ticket = parse_qs(urlparse(r.json()["data"]["set_password_url"]).query)["ticket"][0]
        r = client.post(
            f"{base}/api/v1/auth/set-password",
            json={"ticket": ticket, "new_password": OWNER_PASSWORD},
        )
        assert r.status_code == 200, r.text

        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        redirect = f"{base}/auth/callback"
        r = client.get(
            f"{base}/authorize",
            params={
                "response_type": "code",
                "client_id": "rdm-web",
                "redirect_uri": redirect,
                "state": "s",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "web",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        auth_key = parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]
        r = client.post(
            f"{base}/api/v1/auth/login",
            json={
                "auth_key": auth_key,
                "name": "owner",
                "password": OWNER_PASSWORD,
                "remember": True,
            },
        )
        assert r.status_code == 200, r.text
        code = parse_qs(urlparse(r.json()["data"]["redirect_to"]).query)["code"][0]
        r = client.post(
            f"{base}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": "rdm-web",
                "redirect_uri": redirect,
            },
        )
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        r = client.post(
            f"{base}/api/v1/me/tokens",
            json={"label": "cli-test"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]["token"]


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[str, str]]:
    data_dir = tmp_path / "data"
    initialize_data_dir(data_dir)
    run_upgrade(data_dir)
    port = _free_port()
    settings = Settings(
        data_dir=data_dir,
        port=port,
        extra_redirect_uris=f"http://127.0.0.1:{port}/auth/callback",
    )
    app = create_app(settings)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    base = f"http://127.0.0.1:{port}"
    token = _owner_pat(base)
    try:
        yield base, token
    finally:
        server.should_exit = True
        thread.join(timeout=5)
