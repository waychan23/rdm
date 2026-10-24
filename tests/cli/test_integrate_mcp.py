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
    merge_codex,
    merge_opencode,
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
        app, ["integrate", "mcp", "--data-dir", str(tmp_path / "rdm-data")], env=env
    )
    assert result.exit_code == 0, result.output
    assert "WRITTEN" in result.output
    assert "NO_PROXY=127.0.0.1,localhost" in result.output
    assert "RDM_TOKEN" in result.output
    assert (tmp_path / ".claude.json").exists()
    assert (tmp_path / ".config/opencode/opencode.json").exists()
    assert (tmp_path / ".codex/config.toml").exists()

    # second run: all skipped, still exit 0
    result = runner.invoke(app, ["integrate", "mcp"], env=env)
    assert result.exit_code == 0
    assert "SKIPPED" in result.output


def test_cli_bad_target(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["integrate", "mcp", "--target", "vim"], env={"HOME": str(tmp_path)}
    )
    assert result.exit_code == 2
