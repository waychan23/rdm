"""`rdm integrate mcp`: generate user-level MCP client configs.

Three targets (architecture §9), config merge functions are pure (path in,
path out) for testing:
- claude:   ~/.claude.json            JSON, mcpServers.rdm (${ENV} interpolation)
- opencode: ~/.config/opencode/opencode.json  JSON, top-level mcp.rdm ({env:})
- codex:    ~/.codex/config.toml       TOML, [mcp_servers.rdm] (UNVERIFIED)

JSON writes are atomic (temp file + os.replace) and preserve unrelated keys.
The codex block is wrapped in rdm-managed markers; a conflicting existing
block requires --force (we never splice TOML in place).
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MANAGED_BEGIN = "# >>> rdm-managed >>>"
MANAGED_END = "# <<< rdm-managed <<<"


class IntegrateTarget(StrEnum):
    claude = "claude"
    codex = "codex"
    opencode = "opencode"


@dataclass(frozen=True)
class IntegrateResult:
    target: str
    path: Path
    status: str  # "written" | "skipped" | "conflict"


def claude_config_path(home: Path) -> Path:
    return home / ".claude.json"


def codex_config_path(home: Path) -> Path:
    return home / ".codex" / "config.toml"


def opencode_config_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "opencode.json"


# --- project (directory) scope: one working directory = one member --------


def _bearer_entry(entry_template: dict, token: str) -> dict:
    entry = json.loads(json.dumps(entry_template))
    entry["headers"] = {"Authorization": f"Bearer {token}"}
    return entry


def merge_claude_project(
    home: Path, cwd: Path, url: str, token: str, *, force: bool = False
) -> IntegrateResult:
    """Bind a directory in ~/.claude.json projects[abs_cwd].mcpServers.

    Per-directory config lives in the user-global file (keyed by absolute
    path), so the bound token never lands inside the target repository.
    """
    path = claude_config_path(home)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    projects = data.setdefault("projects", {})
    key = str(cwd.resolve())
    node = projects.setdefault(key, {})
    if not isinstance(node, dict):
        raise ValueError(f"{path}: projects[{key!r}] must be an object")
    servers = node.setdefault("mcpServers", {})
    entry = _bearer_entry(_claude_server(url), token)
    if servers.get("rdm") == entry:
        return IntegrateResult("claude", path, "skipped")
    if "rdm" in servers and not force:
        return IntegrateResult("claude", path, "conflict")
    servers["rdm"] = entry
    _atomic_write_json(path, data)
    return IntegrateResult("claude", path, "written")


def merge_opencode_project(
    cwd: Path, url: str, token: str, *, force: bool = False
) -> tuple[IntegrateResult, bool]:
    """Bind a directory via <cwd>/.opencode/opencode.json.

    Returns (result, gitignore_touched). This file carries a member token,
    so when cwd is a git repo its path is appended to .gitignore.
    """
    path = cwd / ".opencode" / "opencode.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    servers = data.setdefault("mcp", {})
    entry = _bearer_entry(_opencode_server(url), token)
    if servers.get("rdm") == entry:
        return IntegrateResult("opencode", path, "skipped"), False
    if "rdm" in servers and not force:
        return IntegrateResult("opencode", path, "conflict"), False
    servers["rdm"] = entry
    _atomic_write_json(path, data)
    gitignore_touched = _ensure_gitignore(cwd, ".opencode/opencode.json")
    return IntegrateResult("opencode", path, "written"), gitignore_touched


def _ensure_gitignore(cwd: Path, rel_path: str) -> bool:
    """Idempotently append rel_path to <repo>/.gitignore when in a git repo."""
    git_root = cwd
    while git_root != git_root.parent:
        if (git_root / ".git").exists():
            gi = git_root / ".gitignore"
            line = rel_path
            existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
            if line in existing.splitlines():
                return False
            prefix = "" if not existing or existing.endswith("\n") else "\n"
            gi.write_text(existing + f"{prefix}{line}\n", encoding="utf-8")
            return True
        git_root = git_root.parent
    return False


def _claude_server(url: str) -> dict:
    return {
        "type": "http",
        "url": url,
        "headers": {"Authorization": "Bearer ${RDM_TOKEN}"},
    }


def _opencode_server(url: str) -> dict:
    return {
        "type": "remote",
        "url": url,
        "headers": {"Authorization": "Bearer {env:RDM_TOKEN}"},
        "oauth": False,
    }


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge_json_config(
    path: Path,
    *,
    section: tuple[str, ...],
    entry: dict,
    force: bool,
) -> IntegrateResult:
    """Merge one entry under a nested section key in a JSON config file."""
    target = "claude" if section == ("mcpServers",) else "opencode"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path} top-level value must be an object")
    else:
        data = {}

    node = data
    for key in section[:-1]:
        child = node.setdefault(key, {})
        if not isinstance(child, dict):
            raise ValueError(f"{path}: {key} is not an object")
        node = child
    last = section[-1]
    servers = node.setdefault(last, {})
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: {'.'.join(section)} is not an object")

    if servers.get("rdm") == entry:
        return IntegrateResult(target, path, "skipped")
    if "rdm" in servers and not force:
        return IntegrateResult(target, path, "conflict")
    servers["rdm"] = entry
    _atomic_write_json(path, data)
    return IntegrateResult(target, path, "written")


def merge_claude(home: Path, url: str, *, force: bool = False) -> IntegrateResult:
    return merge_json_config(
        claude_config_path(home),
        section=("mcpServers",),
        entry=_claude_server(url),
        force=force,
    )


def merge_opencode(home: Path, url: str, *, force: bool = False) -> IntegrateResult:
    return merge_json_config(
        opencode_config_path(home),
        section=("mcp",),
        entry=_opencode_server(url),
        force=force,
    )


def _codex_block(url: str) -> str:
    return (
        f"{MANAGED_BEGIN}\n"
        "[mcp_servers.rdm]\n"
        f'url = "{url}"\n'
        'bearer_token_env_var = "RDM_TOKEN"\n'
        f"{MANAGED_END}\n"
    )


def _replace_managed_block(text: str, block: str) -> str | None:
    """Swap an existing rdm-managed block; None if no managed block exists."""
    start = text.find(MANAGED_BEGIN)
    if start == -1:
        return None
    end = text.find(MANAGED_END, start)
    if end == -1:
        return None
    end += len(MANAGED_END)
    # consume one trailing newline
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:start] + block + text[end:]


def merge_codex(home: Path, url: str, *, force: bool = False) -> IntegrateResult:
    """Create/update the codex TOML config.

    We never splice user-written TOML: a missing [mcp_servers.rdm] gets an
    appended managed block; a managed block that differs is replaced with
    --force; a hand-written rdm section only yields to --force by rewriting
    the whole file.
    """
    path = codex_config_path(home)
    block = _codex_block(url)
    wanted = {"url": url, "bearer_token_env_var": "RDM_TOKEN"}

    if path.exists():
        text = path.read_text(encoding="utf-8")
        parsed = tomllib.loads(text)
        servers = parsed.get("mcp_servers")
        existing = servers.get("rdm") if isinstance(servers, dict) else None
        if existing == wanted:
            return IntegrateResult("codex", path, "skipped")

        if existing is None:
            new_text = text.rstrip() + "\n\n" + block
        elif MANAGED_BEGIN in text:
            if not force:
                return IntegrateResult("codex", path, "conflict")
            replacement = _replace_managed_block(text, block)
            new_text = replacement if replacement is not None else block
        else:
            # Hand-written [mcp_servers.rdm]: refuse surgical edits.
            if not force:
                return IntegrateResult("codex", path, "conflict")
            new_text = block
    else:
        new_text = block

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)
    return IntegrateResult("codex", path, "written")


MERGERS = {
    IntegrateTarget.claude: merge_claude,
    IntegrateTarget.codex: merge_codex,
    IntegrateTarget.opencode: merge_opencode,
}


def post_install_notes(data_dir: Path) -> list[str]:
    token_path = data_dir / "bootstrap-token"
    return [
        f"export RDM_TOKEN=$(cat {token_path})",
        "export NO_PROXY=127.0.0.1,localhost",
        "restart your agent CLI after editing its MCP config",
    ]
