"""Tests for `rdm skills install` (plan M1-6, architecture §16.32)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rdm.interfaces.cli.main import app
from rdm.interfaces.cli.skills import (
    MANAGED_MARKER,
    SkillTarget,
    bundled_skill_names,
    bundled_skill_text,
    configure_web_origin,
    install_skill,
    normalize_web_origin,
    resolve_target_path,
)


def test_bundled_skills_catalogue() -> None:
    assert bundled_skill_names() == ["rdm-mailbox", "rdm-workflow"]
    assert "work_item_transition" in bundled_skill_text("rdm-workflow")
    # RDM-127: the skill tells agents how to resolve the web origin.
    assert "web_origin" in bundled_skill_text("rdm-workflow")


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


def test_normalize_web_origin() -> None:
    assert normalize_web_origin(" https://rdm.example.com/ ") == "https://rdm.example.com"
    assert normalize_web_origin("http://127.0.0.1:5173") == "http://127.0.0.1:5173"
    for bad in [
        "rdm.example.com",
        "ftp://rdm.example.com",
        "https://rdm.example.com/x",
        "https://x?q=1",
    ]:
        with pytest.raises(ValueError):
            normalize_web_origin(bad)


def test_configure_web_origin_user_config_merges(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = home / ".rdm" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"theme": "dark"}\n', encoding="utf-8")

    written = configure_web_origin("user", "https://rdm.example.com", home=home)
    assert written == path
    assert path.read_text(encoding="utf-8") == (
        '{\n  "theme": "dark",\n  "web_origin": "https://rdm.example.com"\n}\n'
    )


def test_configure_web_origin_project_preserves_binding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    path = repo / ".rdm" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"version": 1, "project": "RDM"}\n', encoding="utf-8")

    configure_web_origin("project", "http://127.0.0.1:5173/", cwd=repo)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": 1,
        "project": "RDM",
        "web_origin": "http://127.0.0.1:5173",
    }


def test_configure_web_origin_rejects_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "home" / ".rdm" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        configure_web_origin("user", "https://rdm.example.com", home=tmp_path / "home")


def test_cli_web_origin_user_scope(tmp_path: Path) -> None:
    runner = CliRunner()
    env = {"HOME": str(tmp_path / "home")}
    result = runner.invoke(
        app,
        [
            "skills",
            "install",
            "--target",
            "claude",
            "--skill",
            "rdm-workflow",
            "--web-origin",
            "https://rdm.example.com",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert "WEB-ORIGIN" in result.output
    config = json.loads((tmp_path / "home/.rdm/config.json").read_text(encoding="utf-8"))
    assert config["web_origin"] == "https://rdm.example.com"


def test_cli_web_origin_project_scope_and_invalid(tmp_path: Path) -> None:
    runner = CliRunner()
    repo = tmp_path / "repo"
    (repo / ".rdm").mkdir(parents=True)
    (repo / ".rdm/project.json").write_text('{"version": 1, "project": "RDM"}\n', encoding="utf-8")
    env = {"HOME": str(tmp_path / "home")}
    result = runner.invoke(
        app,
        [
            "skills",
            "install",
            "--target",
            "claude",
            "--scope",
            "project",
            "--cwd",
            str(repo),
            "--skill",
            "rdm-workflow",
            "--web-origin",
            "http://127.0.0.1:5173",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    data = json.loads((repo / ".rdm/project.json").read_text(encoding="utf-8"))
    assert data == {
        "version": 1,
        "project": "RDM",
        "web_origin": "http://127.0.0.1:5173",
    }

    bad = runner.invoke(
        app,
        [
            "skills",
            "install",
            "--target",
            "claude",
            "--web-origin",
            "https://rdm.example.com/path",
        ],
        env=env,
    )
    assert bad.exit_code == 2
    assert "invalid web origin" in bad.output
