"""Inverse of integrate/skills install: remove rdm MCP entries and skills."""

from __future__ import annotations

import json
from pathlib import Path

from rdm.interfaces.cli import integrate as ig
from rdm.interfaces.cli import skills as sk


def test_remove_claude_user(tmp_path: Path) -> None:
    ig.merge_claude(tmp_path, "http://x/mcp")
    assert json.loads((tmp_path / ".claude.json").read_text())["mcpServers"]["rdm"]
    result = ig.remove_claude(tmp_path)
    assert result.status == "removed"
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert "rdm" not in data["mcpServers"]
    # idempotent: second call absent
    assert ig.remove_claude(tmp_path).status == "absent"


def test_remove_claude_preserves_other_servers(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"rdm": {"url": "u"}, "keep": {"url": "k"}}})
    )
    ig.remove_claude(tmp_path)
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert set(data["mcpServers"]) == {"keep"}


def test_remove_claude_user_scope_cleans_all_project_bindings(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    other = tmp_path / "keep"
    config = {
        "mcpServers": {
            "rdm": {"url": "u"},
            "keep": {"url": "k"},
        },
        "projects": {
            str(repo_a.resolve()): {
                "hasTrustDialogAccepted": True,
                "mcpServers": {"rdm": {"url": "u"}, "keep": {"url": "x"}},
            },
            str(repo_b.resolve()): {
                "mcpServers": {"rdm": {"url": "u"}},
            },
            str(other.resolve()): {
                "mcpServers": {"keep": {"url": "y"}},
            },
        },
    }
    (tmp_path / ".claude.json").write_text(json.dumps(config))

    result = ig.remove_claude(tmp_path)
    assert result.status == "removed"
    assert "2 project binding" in result.detail

    data = json.loads((tmp_path / ".claude.json").read_text())
    assert "rdm" not in data["mcpServers"]
    assert data["mcpServers"]["keep"] == {"url": "k"}
    assert "rdm" not in data["projects"][str(repo_a.resolve())]["mcpServers"]
    assert data["projects"][str(repo_a.resolve())]["hasTrustDialogAccepted"] is True
    assert data["projects"][str(repo_a.resolve())]["mcpServers"]["keep"]
    assert "rdm" not in data["projects"][str(repo_b.resolve())]["mcpServers"]
    assert data["projects"][str(other.resolve())]["mcpServers"]["keep"]
    assert ig.remove_claude(tmp_path).status == "absent"


def test_remove_claude_project_only_binding_reports_removed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (tmp_path / ".claude.json").write_text(
        json.dumps({"projects": {str(repo.resolve()): {"mcpServers": {"rdm": {}}}}})
    )
    result = ig.remove_claude(tmp_path)
    assert result.status == "removed"
    assert result.detail == "1 project binding(s)"


def test_remove_claude_disabled_servers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = {
        "mcpServers": {"rdm": {}, "keep": {}},
        "disabledMcpServers": ["rdm", "keep"],
        "projects": {
            str(repo.resolve()): {
                "mcpServers": {"rdm": {}},
                "disabledMcpServers": ["rdm"],
            },
            str((tmp_path / "other").resolve()): {
                "disabledMcpServers": {"rdm": True, "keep": True},
            },
        },
    }
    (tmp_path / ".claude.json").write_text(json.dumps(config))

    result = ig.remove_claude(tmp_path)
    assert result.status == "removed"
    assert "disabled entry(ies)" in result.detail

    data = json.loads((tmp_path / ".claude.json").read_text())
    assert "rdm" not in data["mcpServers"]
    assert data["disabledMcpServers"] == ["keep"]
    project = data["projects"][str(repo.resolve())]
    assert "rdm" not in project["mcpServers"]
    assert project["disabledMcpServers"] == []
    other = data["projects"][str((tmp_path / "other").resolve())]
    assert other["disabledMcpServers"] == {"keep": True}
    assert ig.remove_claude(tmp_path).status == "absent"


def test_remove_opencode_user(tmp_path: Path) -> None:
    ig.merge_opencode(tmp_path, "http://x/mcp")
    assert ig.remove_opencode(tmp_path).status == "removed"
    data = json.loads((tmp_path / ".config/opencode/opencode.json").read_text())
    assert "rdm" not in data["mcp"]
    assert ig.remove_opencode(tmp_path).status == "absent"


def test_remove_codex_managed_block(tmp_path: Path) -> None:
    ig.merge_codex(tmp_path, "http://x/mcp")
    path = ig.codex_config_path(tmp_path)
    assert ig.MANAGED_BEGIN in path.read_text()
    result = ig.remove_codex(tmp_path)
    assert result.status == "removed"
    text = path.read_text()
    assert ig.MANAGED_BEGIN not in text and "mcp_servers.rdm" not in text
    assert ig.remove_codex(tmp_path).status == "absent"


def test_remove_codex_keeps_user_text(tmp_path: Path) -> None:
    path = ig.codex_config_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('[mcp_servers.other]\nurl = "http://other"\n')
    # no managed block → nothing removed, user content intact
    assert ig.remove_codex(tmp_path).status == "absent"
    assert "mcp_servers.other" in path.read_text()


def test_remove_project_scope_claude(tmp_path: Path) -> None:
    home, cwd = tmp_path / "home", tmp_path / "repo"
    cwd.mkdir()
    # unrelated user-owned project data must survive removal
    claude_json = home / ".claude.json"
    claude_json.parent.mkdir(parents=True, exist_ok=True)
    claude_json.write_text(
        json.dumps({"projects": {str(cwd.resolve()): {"hasTrustDialogAccepted": True}}})
    )
    ig.merge_claude_project(home, cwd, "http://x/mcp", "tok", force=True)
    result = ig.remove_claude_project(home, cwd)
    assert result.status == "removed"
    data = json.loads((home / ".claude.json").read_text())
    node = data["projects"][str(cwd.resolve())]
    assert "rdm" not in node["mcpServers"]
    assert node.get("hasTrustDialogAccepted") is True  # other project keys survive
    assert ig.remove_claude_project(home, cwd).status == "absent"


def test_remove_project_scope_opencode_deletes_file_and_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    ig.merge_opencode_project(repo, "http://x/mcp", "tok", force=True)
    cfg = repo / ".opencode/opencode.json"
    assert cfg.exists()
    assert ".opencode/opencode.json" in (repo / ".gitignore").read_text()

    result, touched = ig.remove_opencode_project(repo)
    assert result.status == "removed" and touched
    assert not cfg.exists()
    assert ".opencode/opencode.json" not in (repo / ".gitignore").read_text()


# --- skills ----------------------------------------------------------------


def test_uninstall_managed_skill(tmp_path: Path) -> None:
    name = sk.bundled_skill_names()[0]
    installed = sk.install_skill(sk.SkillTarget.claude, "user", name, home=tmp_path)
    assert installed.path.exists()
    result = sk.uninstall_skill(sk.SkillTarget.claude, "user", name, home=tmp_path)
    assert result.status == "removed"
    assert not installed.path.parent.exists()  # whole skill directory gone
    assert sk.uninstall_skill(sk.SkillTarget.claude, "user", name, home=tmp_path).status == "absent"


def test_uninstall_refuses_unmanaged_without_force(tmp_path: Path) -> None:
    name = sk.bundled_skill_names()[0]
    dest = sk.resolve_target_path(sk.SkillTarget.claude, "user", name, home=tmp_path, cwd=tmp_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("# user wrote this, not rdm\n")
    result = sk.uninstall_skill(sk.SkillTarget.claude, "user", name, home=tmp_path)
    assert result.status == "unmanaged"
    assert dest.exists()  # untouched
    forced = sk.uninstall_skill(sk.SkillTarget.claude, "user", name, home=tmp_path, force=True)
    assert forced.status == "removed"
    assert not dest.exists()


def test_codex_skill_uses_native_skills_dir(tmp_path: Path) -> None:
    name = sk.bundled_skill_names()[0]
    result = sk.install_skill(sk.SkillTarget.codex, "user", name, home=tmp_path)
    assert result.path == tmp_path / ".codex" / "skills" / name / "SKILL.md"
    assert result.path.exists()
    removed = sk.uninstall_skill(sk.SkillTarget.codex, "user", name, home=tmp_path)
    assert removed.status == "removed" and not removed.path.exists()


# --- through the Typer CLI -------------------------------------------------


def test_cli_uninstall_mcp_and_skills(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from rdm.interfaces.cli.main import app

    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()

    # seed config + a skill
    assert (
        runner.invoke(
            app, ["integrate", "mcp", "--method", "token", "--target", "claude"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["skills", "install", "--target", "claude"]).exit_code == 0

    result = runner.invoke(app, ["uninstall", "mcp", "--target", "claude"])
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert "rdm" not in data.get("mcpServers", {})

    result = runner.invoke(app, ["uninstall", "skills", "--target", "claude"])
    assert result.exit_code == 0, result.output
    # the rdm skill directories are gone (the empty skills/ container is kept)
    skills_dir = tmp_path / ".claude" / "skills"
    if skills_dir.exists():
        assert not list(skills_dir.iterdir())

    # absent config is a non-failure informational run
    again = runner.invoke(app, ["uninstall", "mcp", "--target", "claude"])
    assert again.exit_code == 0


def test_cli_uninstall_project_requires_cwd(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from rdm.interfaces.cli.main import app

    result = CliRunner().invoke(
        app, ["uninstall", "mcp", "--scope", "project", "--target", "claude"]
    )
    assert result.exit_code == 2
