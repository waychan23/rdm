"""`rdm skills install`: distribute bundled skills to agent CLIs.

Bundled canonical skills live in rdm.resources/skills/<name>/SKILL.md.
Target path conventions (architecture §16.32):
- claude: native skills — ~/.claude/skills/<name>/SKILL.md, .claude/skills/...
- codex: no native skill concept, thin shell in prompts dir (UNVERIFIED)
- opencode: native skills (verified 1.18.35 via `opencode debug skill`) —
  ~/.config/opencode/skills/<name>/SKILL.md, .opencode/skills/...

Installs are idempotent byte copies carrying an rdm-managed marker; a
content conflict requires --force.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from pathlib import Path

MANAGED_MARKER = "<!-- rdm-managed: do not edit; reinstall with `rdm skills install` -->"


class SkillTarget(StrEnum):
    claude = "claude"
    codex = "codex"
    opencode = "opencode"


@dataclass(frozen=True)
class InstallResult:
    skill: str
    target: str
    scope: str
    path: Path
    status: str  # "installed" | "skipped" | "conflict"


def bundled_skill_names() -> list[str]:
    """Names of all bundled skills (directories containing SKILL.md)."""
    root = files("rdm.resources").joinpath("skills")
    names = [p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()]
    return sorted(names)


def bundled_skill_text(skill_name: str) -> str:
    """Read a bundled SKILL.md; raises FileNotFoundError if unknown."""
    if skill_name not in bundled_skill_names():
        raise FileNotFoundError(f"no bundled skill named {skill_name!r}")
    return (
        files("rdm.resources")
        .joinpath("skills", skill_name, "SKILL.md")
        .read_text(encoding="utf-8")
    )


def resolve_target_path(
    target: SkillTarget,
    scope: str,
    skill_name: str,
    *,
    home: Path,
    cwd: Path,
) -> Path:
    """Resolve the destination file for a skill installation.

    Pure function (all base paths injected) for testability.
    """
    if scope == "user":
        if target is SkillTarget.claude:
            return home / ".claude" / "skills" / skill_name / "SKILL.md"
        if target is SkillTarget.codex:
            return home / ".codex" / "prompts" / f"{skill_name}.md"
        return home / ".config" / "opencode" / "skills" / skill_name / "SKILL.md"
    if scope == "project":
        if target is SkillTarget.claude:
            return cwd / ".claude" / "skills" / skill_name / "SKILL.md"
        if target is SkillTarget.codex:
            return cwd / ".codex" / "prompts" / f"{skill_name}.md"
        return cwd / ".opencode" / "skills" / skill_name / "SKILL.md"
    raise ValueError(f"scope must be 'user' or 'project', got {scope!r}")


def _install_text(canonical: str) -> str:
    """Insert the managed marker directly after YAML frontmatter."""
    if canonical.startswith("---\n"):
        end = canonical.find("\n---\n", 4)
        if end != -1:
            cut = end + len("\n---\n")
            return canonical[:cut] + "\n" + MANAGED_MARKER + "\n" + canonical[cut:]
    return MANAGED_MARKER + "\n\n" + canonical


def install_skill(
    target: SkillTarget,
    scope: str,
    skill_name: str,
    *,
    force: bool = False,
    home: Path | None = None,
    cwd: Path | None = None,
) -> InstallResult:
    """Install one bundled skill to one destination. Idempotent."""
    home = home or Path.home()
    cwd = cwd or Path.cwd()
    dest = resolve_target_path(target, scope, skill_name, home=home, cwd=cwd)
    content = _install_text(bundled_skill_text(skill_name))

    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        if existing == content:
            return InstallResult(skill_name, target.value, scope, dest, "skipped")
        # Different content (user-edited or a stale managed copy): require
        # an explicit --force so reinstalls never clobber local changes.
        if not force:
            return InstallResult(skill_name, target.value, scope, dest, "conflict")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return InstallResult(skill_name, target.value, scope, dest, "installed")
