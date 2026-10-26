"""Bind throwaway member workdirs to the test server (project-scope MCP)."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from rdm.interfaces.cli import skills as skills_mod
from rdm.interfaces.cli.integrate import (
    merge_claude_project,
    merge_opencode_project,
)


def bind_member(cwd: Path, url: str, token: str) -> None:
    # IMPORTANT: cwd must NOT live inside a git repo. claude-code resolves the
    # session project root to the enclosing .git root and reads
    # ~/.claude.json projects[<git-root>].mcpServers, ignoring entries keyed
    # at deeper subdirectories. Harness workdirs therefore live in the OS
    # temp area (see Harness.member).
    cwd.mkdir(parents=True, exist_ok=True)
    merge_claude_project(Path.home(), cwd, url, token, force=True)
    merge_opencode_project(cwd, url, token, force=True)
    # Skills inside the workdir are picked up by both CLIs.
    for target in (skills_mod.SkillTarget.claude, skills_mod.SkillTarget.opencode):
        for name in skills_mod.bundled_skill_names():
            skills_mod.install_skill(target, "project", name, cwd=cwd, force=True)
    _preflight(url, token)


def _preflight(url: str, token: str) -> None:
    """Verify the bound URL/token completes an MCP initialize handshake."""
    import asyncio

    headers = {"Authorization": f"Bearer {token}"}
    transport = StreamableHttpTransport(
        url,
        headers=headers,
        httpx_client_factory=lambda **kw: httpx.AsyncClient(
            timeout=10, trust_env=False, headers=kw["headers"]
        ),
    )

    async def handshake() -> None:
        async with Client(transport) as client:
            tools = await client.list_tools()
            assert len(tools) >= 27, f"expected 27 tools, got {len(tools)}"

    asyncio.run(handshake())


def cleanup(cwd: Path) -> None:
    """Remove opencode config from temp; claude binding lives in ~/.claude.json
    keyed by this unique path and is removed there by the runner."""
    shutil.rmtree(cwd, ignore_errors=True)


def remove_claude_key(cwd: Path) -> None:
    import json

    path = Path.home() / ".claude.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data.get("projects", {}).pop(str(cwd.resolve()), None)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
