"""Tests for `rdm integrate mcp` (plan M1-7, architecture §9)."""

import json
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from rdm.interfaces.cli.integrate import (
    MANAGED_BEGIN,
    MANAGED_END,
    claude_config_path,
    codex_config_path,
    merge_claude,
    merge_claude_project,
    merge_codex,
    merge_opencode,
    merge_opencode_project,
    opencode_config_path,
)
from rdm.interfaces.cli.main import app

URL = "http://127.0.0.1:8765/mcp"


def test_claude_create_and_idempotent(tmp_path: Path) -> None:
    path = claude_config_path(tmp_path)
    r1 = merge_claude(tmp_path, URL)
    assert r1.status == "written"
    data = json.loads(path.read_text())
    assert data["mcpServers"]["rdm"]["url"] == URL
    assert data["mcpServers"]["rdm"]["headers"]["Authorization"] == "Bearer ${RDM_TOKEN}"

    r2 = merge_claude(tmp_path, URL)
    assert r2.status == "skipped"


def test_claude_preserves_other_keys_and_servers(tmp_path: Path) -> None:
    path = claude_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"other": {"type": "http", "url": "x"}}}),
        encoding="utf-8",
    )
    merge_claude(tmp_path, URL)
    data = json.loads(path.read_text())
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"]["url"] == "x"
    assert data["mcpServers"]["rdm"]["type"] == "http"


def test_claude_conflict_and_force(tmp_path: Path) -> None:
    merge_claude(tmp_path, URL)
    r = merge_claude(tmp_path, "http://example/mcp")
    assert r.status == "conflict"
    assert json.loads(claude_config_path(tmp_path).read_text())["mcpServers"]["rdm"]["url"] == URL
    r = merge_claude(tmp_path, "http://example/mcp", force=True)
    assert r.status == "written"
    assert (
        json.loads(claude_config_path(tmp_path).read_text())["mcpServers"]["rdm"]["url"]
        == "http://example/mcp"
    )


def test_broken_json_not_overwritten(tmp_path: Path) -> None:
    path = claude_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    try:
        merge_claude(tmp_path, URL)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert path.read_text() == "{not json"


def test_opencode_shape_and_merge(tmp_path: Path) -> None:
    path = opencode_config_path(tmp_path)
    merge_opencode(tmp_path, URL)
    data = json.loads(path.read_text())
    entry = data["mcp"]["rdm"]
    assert entry["type"] == "remote"
    assert entry["oauth"] is False
    assert entry["headers"]["Authorization"] == "Bearer {env:RDM_TOKEN}"

    path.write_text(json.dumps({"model": "x", "mcp": {}}), encoding="utf-8")
    merge_opencode(tmp_path, URL)
    data = json.loads(path.read_text())
    assert data["model"] == "x"
    assert data["mcp"]["rdm"]["url"] == URL


def test_codex_new_file_parses(tmp_path: Path) -> None:
    r = merge_codex(tmp_path, URL)
    assert r.status == "written"
    path = codex_config_path(tmp_path)
    parsed = tomllib.loads(path.read_text())
    assert parsed["mcp_servers"]["rdm"] == {
        "url": URL,
        "bearer_token_env_var": "RDM_TOKEN",
    }
    assert MANAGED_BEGIN in path.read_text()


def test_codex_idempotent_and_appends_to_existing(tmp_path: Path) -> None:
    assert merge_codex(tmp_path, URL).status == "written"
    assert merge_codex(tmp_path, URL).status == "skipped"

    path = codex_config_path(tmp_path)
    prefix = '[mcp_servers.other]\nurl = "http://other"\n\n'
    path.write_text(prefix + path.read_text(), encoding="utf-8")
    # still skipped: rdm values unchanged
    assert merge_codex(tmp_path, URL).status == "skipped"
    parsed = tomllib.loads(path.read_text())
    assert set(parsed["mcp_servers"]) == {"other", "rdm"}


def test_codex_managed_block_conflict_force(tmp_path: Path) -> None:
    merge_codex(tmp_path, URL)
    assert merge_codex(tmp_path, "http://other/mcp").status == "conflict"
    r = merge_codex(tmp_path, "http://other/mcp", force=True)
    assert r.status == "written"
    parsed = tomllib.loads(codex_config_path(tmp_path).read_text())
    assert parsed["mcp_servers"]["rdm"]["url"] == "http://other/mcp"
    # exactly one managed block remains
    text = codex_config_path(tmp_path).read_text()
    assert text.count(MANAGED_BEGIN) == 1 and text.count(MANAGED_END) == 1


def test_codex_handwritten_section_conflicts(tmp_path: Path) -> None:
    path = codex_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[mcp_servers.rdm]\nurl = "mine"\n', encoding="utf-8")
    assert merge_codex(tmp_path, URL).status == "conflict"
    assert path.read_text() == '[mcp_servers.rdm]\nurl = "mine"\n'


def test_cli_all_targets_and_notes(tmp_path: Path) -> None:
    runner = CliRunner()
    env = {"HOME": str(tmp_path)}
    result = runner.invoke(
        app,
        ["integrate", "mcp", "--method", "token", "--data-dir", str(tmp_path / "rdm-data")],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert "WRITTEN" in result.output
    assert "NO_PROXY=127.0.0.1,localhost" in result.output
    assert "RDM_TOKEN" in result.output
    assert (tmp_path / ".claude.json").exists()
    assert (tmp_path / ".config/opencode/opencode.json").exists()
    assert (tmp_path / ".codex/config.toml").exists()

    # second run: all skipped, still exit 0
    result = runner.invoke(app, ["integrate", "mcp", "--method", "token"], env=env)
    assert result.exit_code == 0
    assert "SKIPPED" in result.output


def test_cli_oauth_method_writes_no_static_credentials(tmp_path: Path) -> None:
    runner = CliRunner()
    env = {"HOME": str(tmp_path)}
    result = runner.invoke(app, ["integrate", "mcp", "--method", "oauth"], env=env)
    assert result.exit_code == 0, result.output
    assert "WRITTEN" in result.output
    assert "RDM_TOKEN" not in result.output  # no static-token export hint

    claude = json.loads((tmp_path / ".claude.json").read_text())
    assert claude["mcpServers"]["rdm"] == {"type": "http", "url": URL}
    opencode = json.loads((tmp_path / ".config/opencode/opencode.json").read_text())
    assert opencode["mcp"]["rdm"] == {"type": "remote", "url": URL}
    codex = (tmp_path / ".codex/config.toml").read_text()
    assert "url = " in codex and "bearer_token_env_var" not in codex

    # Idempotent.
    assert runner.invoke(app, ["integrate", "mcp", "--method", "oauth"], env=env).exit_code == 0


def test_cli_project_oauth_writes_no_token(tmp_path: Path) -> None:
    home, cwd = tmp_path / "home", tmp_path / "repo"
    cwd.mkdir(parents=True)
    result = CliRunner().invoke(
        app,
        [
            "integrate",
            "mcp",
            "--scope",
            "project",
            "--method",
            "oauth",
            "--target",
            "claude",
            "--url",
            URL,
            "--cwd",
            str(cwd),
        ],
        env={"HOME": str(home)},
    )
    assert result.exit_code == 0, result.output
    data = json.loads((home / ".claude.json").read_text())
    entry = data["projects"][str(cwd.resolve())]["mcpServers"]["rdm"]
    assert entry == {"type": "http", "url": URL}


def test_cli_bad_target(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["integrate", "mcp", "--target", "vim"], env={"HOME": str(tmp_path)}
    )
    assert result.exit_code == 2


# --- project (directory) scope ---


def test_claude_project_bind_idempotent_conflict_force(tmp_path: Path) -> None:
    home, cwd = tmp_path / "home", tmp_path / "repo"
    cwd.mkdir(parents=True)
    r1 = merge_claude_project(home, cwd, URL, "tok-1")
    assert r1.status == "written"
    data = json.loads((home / ".claude.json").read_text())
    entry = data["projects"][str(cwd.resolve())]["mcpServers"]["rdm"]
    assert entry["headers"]["Authorization"] == "Bearer tok-1"

    assert merge_claude_project(home, cwd, URL, "tok-1").status == "skipped"
    assert merge_claude_project(home, cwd, URL, "tok-2").status == "conflict"
    r4 = merge_claude_project(home, cwd, URL, "tok-2", force=True)
    assert r4.status == "written"
    data = json.loads((home / ".claude.json").read_text())
    assert data["projects"][str(cwd.resolve())]["mcpServers"]["rdm"]["headers"] == {
        "Authorization": "Bearer tok-2"
    }


def test_claude_project_bind_preserves_other_project_data(tmp_path: Path) -> None:
    home, cwd = tmp_path / "home", tmp_path / "repo"
    cwd.mkdir(parents=True)
    claude_json = home / ".claude.json"
    claude_json.parent.mkdir(parents=True, exist_ok=True)
    claude_json.write_text(
        json.dumps({"projects": {str(cwd.resolve()): {"hasTrustDialogAccepted": True}}}),
        encoding="utf-8",
    )
    merge_claude_project(home, cwd, URL, "t")
    data = json.loads(claude_json.read_text())
    node = data["projects"][str(cwd.resolve())]
    assert node["hasTrustDialogAccepted"] is True
    assert node["mcpServers"]["rdm"]["url"] == URL


def test_opencode_project_bind_and_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    result, touched = merge_opencode_project(repo, URL, "tok")
    assert result.status == "written" and touched
    cfg = json.loads((repo / ".opencode" / "opencode.json").read_text())
    assert cfg["mcp"]["rdm"]["type"] == "remote"
    assert cfg["mcp"]["rdm"]["headers"]["Authorization"] == "Bearer tok"
    assert ".opencode/opencode.json" in (repo / ".gitignore").read_text()

    # second run: skipped, gitignore not duplicated
    result2, touched2 = merge_opencode_project(repo, URL, "tok")
    assert result2.status == "skipped" and not touched2
    assert (repo / ".gitignore").read_text().count(".opencode/opencode.json") == 1

    # outside a git repo: still written, no gitignore
    plain = tmp_path / "plain"
    result3, touched3 = merge_opencode_project(plain, URL, "tok")
    assert result3.status == "written" and not touched3
    assert not (plain / ".gitignore").exists()
