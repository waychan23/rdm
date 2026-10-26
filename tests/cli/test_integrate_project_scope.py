"""End-to-end: directory-scoped MCP binding acts as the bound member."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from rdm.interfaces.cli.main import app


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_project_scope_binds_member_token_to_directory(tmp_path: Path, live_server) -> None:
    base, owner_token = live_server
    headers = _auth(owner_token)
    client = httpx.Client(timeout=10, trust_env=False)

    # project + two members (frontend/backend agents)
    r = client.post(f"{base}/api/v1/projects", json={"key": "DEMO", "name": "D"}, headers=headers)
    assert r.status_code == 201, r.text
    for name in ("frontend", "backend"):
        r = client.post(
            f"{base}/api/v1/projects/DEMO/members",
            json={"name": name, "type": "human", "roles": ["worker"]},
            headers=headers,
        )
        assert r.status_code == 201, r.text

    home, fe_dir, be_dir = (
        tmp_path / "home",
        tmp_path / "repos" / "frontend-app",
        tmp_path / "repos" / "backend-app",
    )
    fe_dir.mkdir(parents=True)
    be_dir.mkdir(parents=True)
    runner = CliRunner()

    def bind(directory: Path, member: str, target: str) -> object:
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
                "--member",
                member,
                "--project",
                "DEMO",
                "--url",
                f"{base}/mcp",
                "--cwd",
                str(directory),
            ],
            env={"HOME": str(home), "RDM_TOKEN": owner_token},
        )

    # claude: ~/.claude.json keyed by absolute path
    result = bind(fe_dir, "frontend", "claude")
    assert result.exit_code == 0, result.output
    data = json.loads((home / ".claude.json").read_text())
    fe_token = data["projects"][str(fe_dir.resolve())]["mcpServers"]["rdm"]["headers"][
        "Authorization"
    ].removeprefix("Bearer ")

    result = bind(be_dir, "backend", "claude")
    assert result.exit_code == 0, result.output
    data = json.loads((home / ".claude.json").read_text())
    be_token = data["projects"][str(be_dir.resolve())]["mcpServers"]["rdm"]["headers"][
        "Authorization"
    ].removeprefix("Bearer ")
    assert fe_token != be_token

    # each bound token authenticates as its own member, project via whoami
    who_fe = client.get(f"{base}/api/v1/whoami", headers=_auth(fe_token)).json()["data"]
    who_be = client.get(f"{base}/api/v1/whoami", headers=_auth(be_token)).json()["data"]
    assert who_fe["member"]["name"] == "frontend"
    assert who_be["member"]["name"] == "backend"
    assert who_fe["project"]["key"] == "DEMO"

    # idempotent when the same token is re-bound; re-issuing a new token
    # intentionally yields a conflict (rotate with --force).
    same = runner.invoke(
        app,
        [
            "integrate",
            "mcp",
            "--scope",
            "project",
            "--method",
            "token",
            "--target",
            "claude",
            "--member-token",
            fe_token,
            "--url",
            f"{base}/mcp",
            "--cwd",
            str(fe_dir),
        ],
        env={"HOME": str(home)},
    )
    assert same.exit_code == 0, same.output
    data2 = json.loads((home / ".claude.json").read_text())
    assert (
        data2["projects"][str(fe_dir.resolve())]["mcpServers"]["rdm"]["headers"]["Authorization"]
        == f"Bearer {fe_token}"
    )

    # opencode: in-repo config with the same bound token + gitignore
    (fe_dir / ".git").mkdir()
    result = runner.invoke(
        app,
        [
            "integrate",
            "mcp",
            "--scope",
            "project",
            "--method",
            "token",
            "--target",
            "opencode",
            "--member-token",
            fe_token,
            "--url",
            f"{base}/mcp",
            "--cwd",
            str(fe_dir),
        ],
        env={"HOME": str(home)},
    )
    assert result.exit_code == 0, result.output
    cfg = json.loads((fe_dir / ".opencode" / "opencode.json").read_text())
    assert cfg["mcp"]["rdm"]["headers"]["Authorization"] == f"Bearer {fe_token}"
    assert ".opencode/opencode.json" in (fe_dir / ".gitignore").read_text()

    # codex project scope unsupported
    result = bind(fe_dir, "frontend", "codex")
    assert result.exit_code == 2

    # missing member
    result = runner.invoke(
        app,
        [
            "integrate",
            "mcp",
            "--scope",
            "project",
            "--method",
            "token",
            "--member",
            "ghost",
            "--project",
            "DEMO",
            "--url",
            f"{base}/mcp",
            "--cwd",
            str(fe_dir),
        ],
        env={"HOME": str(home), "RDM_TOKEN": owner_token},
    )
    assert result.exit_code == 1

    client.close()
