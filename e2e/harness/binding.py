"""Bind throwaway member workdirs to the test server (project-scope MCP)."""

from __future__ import annotations

import shutil
from pathlib import Path

from rdm.interfaces.cli import skills as skills_mod
from rdm.interfaces.cli.integrate import (
    merge_claude_project,
    merge_opencode_project,
)


def bind_member(cwd: Path, url: str, token: str) -> None:
    cwd.mkdir(parents=True, exist_ok=True)
    merge_claude_project(Path.home(), cwd, url, token, force=True)
    merge_opencode_project(cwd, url, token, force=True)
    # Skills inside the workdir are picked up by both CLIs.
    for target in (skills_mod.SkillTarget.claude, skills_mod.SkillTarget.opencode):
        for name in skills_mod.bundled_skill_names():
            skills_mod.install_skill(target, "project", name, cwd=cwd, force=True)


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
