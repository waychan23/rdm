"""Tests for `rdm skills install` (plan M1-6, architecture §16.32)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from rdm.interfaces.cli.main import app
from rdm.interfaces.cli.skills import (
    MANAGED_MARKER,
    SkillTarget,
    bundled_skill_names,
    bundled_skill_text,
    install_skill,
    resolve_target_path,
)


def test_bundled_skills_catalogue() -> None:
    assert bundled_skill_names() == ["rdm-mailbox", "rdm-workflow"]
    assert "work_item_transition" in bundled_skill_text("rdm-workflow")


@pytest.mark.parametrize(
    "target,scope,relative",
    [
        ("claude", "user", ".claude/skills/rdm-workflow/SKILL.md"),
        ("codex", "user", ".codex/skills/rdm-workflow/SKILL.md"),
        ("opencode", "user", ".config/opencode/skills/rdm-workflow/SKILL.md"),
        ("claude", "project", ".claude/skills/rdm-workflow/SKILL.md"),
        ("codex", "project", ".codex/skills/rdm-workflow/SKILL.md"),
        ("opencode", "project", ".opencode/skills/rdm-workflow/SKILL.md"),
    ],
)
def test_target_paths_six_locations(tmp_path: Path, target: str, scope: str, relative: str) -> None:
    home, cwd = tmp_path / "home", tmp_path / "proj"
    path = resolve_target_path(SkillTarget(target), scope, "rdm-workflow", home=home, cwd=cwd)
    base = home if scope == "user" else cwd
    assert path == base / relative


def test_resolve_path_rejects_bad_scope(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_target_path(SkillTarget.claude, "global", "x", home=tmp_path, cwd=tmp_path)


def test_install_idempotent_conflict_force(tmp_path: Path) -> None:
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    r1 = install_skill(SkillTarget.claude, "user", "rdm-workflow", home=home, cwd=cwd)
    assert r1.status == "installed"
    dest = r1.path
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert MANAGED_MARKER in content
    assert "work_item_transition" in content

    # identical content -> skipped
    r2 = install_skill(SkillTarget.claude, "user", "rdm-workflow", home=home, cwd=cwd)
    assert r2.status == "skipped"

    # local edit -> conflict without --force
    dest.write_text(content + "\nuser edit\n", encoding="utf-8")
    r3 = install_skill(SkillTarget.claude, "user", "rdm-workflow", home=home, cwd=cwd)
    assert r3.status == "conflict"
    assert "user edit" in dest.read_text(encoding="utf-8")

    # --force overwrites
    r4 = install_skill(SkillTarget.claude, "user", "rdm-workflow", force=True, home=home, cwd=cwd)
    assert r4.status == "installed"
    assert dest.read_text(encoding="utf-8") == content


def test_user_owned_file_is_conflict(tmp_path: Path) -> None:
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    dest = resolve_target_path(SkillTarget.opencode, "user", "rdm-workflow", home=home, cwd=cwd)
    dest.parent.mkdir(parents=True)
    dest.write_text("# my own command\n", encoding="utf-8")
    r = install_skill(SkillTarget.opencode, "user", "rdm-workflow", home=home, cwd=cwd)
    assert r.status == "conflict"
    assert dest.read_text(encoding="utf-8") == "# my own command\n"


def test_unknown_skill_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        install_skill(SkillTarget.claude, "user", "nope", home=tmp_path / "h", cwd=tmp_path / "c")


def test_cli_install_and_skip(tmp_path: Path) -> None:
    runner = CliRunner()
    env = {"HOME": str(tmp_path / "home")}

    result = runner.invoke(
        app, ["skills", "install", "--target", "claude", "--scope", "user"], env=env
    )
    assert result.exit_code == 0, result.output
    assert "INSTALLED" in result.output
    assert (tmp_path / "home/.claude/skills/rdm-workflow/SKILL.md").exists()

    result = runner.invoke(app, ["skills", "install", "--target", "claude"], env=env)
    assert result.exit_code == 0, result.output
    assert "SKIPPED" in result.output


def test_cli_conflict_exits_two(tmp_path: Path) -> None:
    runner = CliRunner()
    env = {"HOME": str(tmp_path / "home")}
    dest = tmp_path / "home/.claude/skills/rdm-workflow/SKILL.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("user content", encoding="utf-8")

    result = runner.invoke(app, ["skills", "install", "--target", "claude"], env=env)
    assert result.exit_code == 2
    assert "CONFLICT" in result.output


def test_cli_bad_target_and_unknown_skill(tmp_path: Path) -> None:
    runner = CliRunner()
    env = {"HOME": str(tmp_path / "home")}
    result = runner.invoke(app, ["skills", "install", "--target", "vim"], env=env)
    assert result.exit_code == 2
    result = runner.invoke(
        app, ["skills", "install", "--target", "claude", "--skill", "ghost"], env=env
    )
    assert result.exit_code == 2


def test_cli_project_scope_requires_cwd(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["skills", "install", "--target", "claude", "--scope", "project"],
        env={"HOME": str(tmp_path / "home")},
    )
    assert result.exit_code == 2
    assert "requires --cwd" in result.output


def test_cli_project_scope_installs_into_cwd(tmp_path: Path) -> None:
    runner = CliRunner()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = runner.invoke(
        app,
        [
            "skills",
            "install",
            "--target",
            "codex",
            "--scope",
            "project",
            "--cwd",
            str(repo),
            "--skill",
            "rdm-workflow",
        ],
        env={"HOME": str(tmp_path / "home")},
    )
    assert result.exit_code == 0, result.output
    dest = repo / ".codex" / "skills" / "rdm-workflow" / "SKILL.md"
    assert dest.exists()
    assert "rdm-managed" in dest.read_text(encoding="utf-8")
