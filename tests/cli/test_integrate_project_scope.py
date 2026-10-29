"""End-to-end: directory-scoped MCP binding acts as the bound member."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from typer.testing import CliRunner

from rdm.interfaces.cli.main import app


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_project_scope_binds_user_token_to_directory(tmp_path: Path, live_server) -> None:
    base, owner_token = live_server
    headers = _auth(owner_token)
    client = httpx.Client(timeout=10, trust_env=False)

    r = client.post(f"{base}/api/v1/projects", json={"key": "DEMO", "name": "D"}, headers=headers)
    assert r.status_code == 201, r.text

    # Two humans with their own PATs; no administrator ever mints tokens.
    tokens = {}
    for name in ("frontend", "backend"):
        r = client.post(f"{base}/api/v1/users", json={"name": name}, headers=headers)
        assert r.status_code == 201, r.text
        reset_url = r.json()["data"]["password_reset_url"]
        ticket = parse_qs(urlparse(reset_url).query)["ticket"][0]
        r = client.post(
            f"{base}/api/v1/auth/set-password",
            json={"ticket": ticket, "new_password": "Passw0rd123"},
        )
        assert r.status_code == 200, r.text
        users = client.get(f"{base}/api/v1/users", headers=headers).json()["data"]
        uid = next(u["id"] for u in users if u["name"] == name)
        r = client.post(
            f"{base}/api/v1/projects/DEMO/members",
            json={"user_id": uid, "roles": ["worker"]},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        tokens[name] = _login_pat_sync(client, base, name)

    home, fe_dir, be_dir = (
        tmp_path / "home",
        tmp_path / "repos" / "frontend-app",
        tmp_path / "repos" / "backend-app",
    )
    fe_dir.mkdir(parents=True)
    be_dir.mkdir(parents=True)
    runner = CliRunner()

    def bind(directory: Path, token: str, target: str) -> object:
        return runner.invoke(
            app,
            [
                "integrate",
                "mcp",
                "--scope",
                "project",
                "--method",
                "token",
                "--target",
                target,
                "--member-token",
                token,
                "--url",
                f"{base}/mcp",
                "--cwd",
                str(directory),
            ],
            env={"HOME": str(home)},
        )

    result = bind(fe_dir, tokens["frontend"], "claude")
    assert result.exit_code == 0, result.output
    data = json.loads((home / ".claude.json").read_text())
    fe_token = data["projects"][str(fe_dir.resolve())]["mcpServers"]["rdm"]["headers"][
        "Authorization"
    ].removeprefix("Bearer ")

    result = bind(be_dir, tokens["backend"], "claude")
    assert result.exit_code == 0, result.output
    data = json.loads((home / ".claude.json").read_text())
    be_token = data["projects"][str(be_dir.resolve())]["mcpServers"]["rdm"]["headers"][
        "Authorization"
    ].removeprefix("Bearer ")
    assert fe_token != be_token

    who_fe = client.get(f"{base}/api/v1/whoami", headers=_auth(fe_token)).json()["data"]
    who_be = client.get(f"{base}/api/v1/whoami", headers=_auth(be_token)).json()["data"]
    assert who_fe["identity"]["name"] == "frontend"
    assert who_be["identity"]["name"] == "backend"
    assert {p["key"] for p in who_fe["projects"]} == {"DEMO"}

    # Idempotent when the same token is re-bound.
    same = bind(fe_dir, fe_token, "claude")
    assert same.exit_code == 0, same.output
    data2 = json.loads((home / ".claude.json").read_text())
    assert (
        data2["projects"][str(fe_dir.resolve())]["mcpServers"]["rdm"]["headers"]["Authorization"]
        == f"Bearer {fe_token}"
    )

    # opencode: in-repo config with the same bound token + gitignore
    (fe_dir / ".git").mkdir()
    result = bind(fe_dir, fe_token, "opencode")
    assert result.exit_code == 0, result.output
    cfg = json.loads((fe_dir / ".opencode" / "opencode.json").read_text())
    assert cfg["mcp"]["rdm"]["headers"]["Authorization"] == f"Bearer {fe_token}"
    assert ".opencode/opencode.json" in (fe_dir / ".gitignore").read_text()

    # codex project scope unsupported
    result = bind(fe_dir, fe_token, "codex")
    assert result.exit_code == 2

    # Static-token binding without a token is refused (no admin issuance).
    result = runner.invoke(
        app,
        [
            "integrate",
            "mcp",
            "--scope",
            "project",
            "--method",
            "token",
            "--url",
            f"{base}/mcp",
            "--cwd",
            str(fe_dir),
        ],
        env={"HOME": str(home)},
    )
    assert result.exit_code == 2

    client.close()


def _login_pat_sync(client: httpx.Client, base: str, name: str) -> str:
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
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
            "scope": "mcp",
        },
        follow_redirects=False,
    )
    auth_key = parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]
    r = client.post(
        f"{base}/api/v1/auth/login",
        json={"auth_key": auth_key, "name": name, "password": "Passw0rd123", "remember": True},
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
        json={"label": "cli"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["token"]
