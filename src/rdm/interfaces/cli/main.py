"""`rdm` command-line interface (Typer).

M0 commands: init / serve / db upgrade|downgrade|status / member ...
M1 commands: skills install, integrate mcp. doctor lands in M2.
Admin commands are thin HTTP clients except init/db, which talk to the
database directly (see docs/architecture.md §7).
"""

from pathlib import Path
from typing import Annotated, Literal

import typer

from rdm import __version__

DEFAULT_DATA_DIR = Path.home() / "rdm-data"
DEFAULT_URL = "http://127.0.0.1:8765"

DataDirOpt = Annotated[Path, typer.Option("--data-dir", envvar="RDM_DATA_DIR")]
UrlOpt = Annotated[str, typer.Option("--url", envvar="RDM_SERVER_URL")]
TokenOpt = Annotated[str | None, typer.Option("--token", envvar="RDM_TOKEN")]
TokenDataDirOpt = Annotated[Path | None, typer.Option("--data-dir", envvar="RDM_DATA_DIR")]
ProjectOpt = Annotated[str | None, typer.Option("--project", envvar="RDM_PROJECT")]

app = typer.Typer(
    name="rdm",
    help="rd-manager — human/agent collaborative R&D work management.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="Database migration commands (direct DB connection).")
account_app = typer.Typer(help="Offline account recovery (direct DB connection).")
project_app = typer.Typer(help="List or create projects (API client).")
member_app = typer.Typer(help="Manage project members and tokens (API client).")
token_app = typer.Typer(help="Issue or revoke member tokens.")
skills_app = typer.Typer(help="Install bundled skills into agent CLIs.")
integrate_app = typer.Typer(help="Generate agent integration configs.")
uninstall_app = typer.Typer(
    help="Remove rdm MCP configs and skills from agent CLIs (inverse of install/integrate)."
)

app.add_typer(db_app, name="db")
app.add_typer(account_app, name="account")
app.add_typer(project_app, name="project")
app.add_typer(member_app, name="member")
member_app.add_typer(token_app, name="token")
app.add_typer(skills_app, name="skills")
app.add_typer(integrate_app, name="integrate")
app.add_typer(uninstall_app, name="uninstall")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    pass


@app.command()
def init(data_dir: DataDirOpt = DEFAULT_DATA_DIR) -> None:
    """Initialize a data directory and upgrade the database to head."""
    from rdm.interfaces.cli import db as db_commands

    db_commands.initialize_data_dir(data_dir)
    db_commands.run_upgrade(data_dir)
    typer.secho(f"Initialized {data_dir}", fg=typer.colors.GREEN)


@app.command()
def serve(
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
    host: Annotated[str, typer.Option("--host", envvar="RDM_HOST")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", envvar="RDM_PORT")] = 8765,
    web_ui: Annotated[
        Literal["next", "legacy"],
        typer.Option(
            "--web-ui",
            envvar="RDM_WEB_UI",
            help="SPA bundle to serve: next (React+ADS, default) | legacy (frozen Vue app).",
        ),
    ] = "next",
) -> None:
    """Start the HTTP + MCP server (loopback binds only)."""
    from rdm.interfaces.cli import server as server_commands

    server_commands.run_serve(data_dir, host, port, web_ui)


@app.command("bootstrap-token")
def bootstrap_token(
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
    keep_old: Annotated[
        bool, typer.Option("--keep-old", help="Do not revoke previous bootstrap PATs.")
    ] = False,
) -> None:
    """Rotate the bootstrap owner PAT and rewrite data-dir/bootstrap-token."""
    from rdm.interfaces.cli import account as account_commands

    raw = account_commands.rotate_bootstrap_token(data_dir, keep_old=keep_old)
    token_path = data_dir / "bootstrap-token"
    typer.secho(f"new bootstrap token written to {token_path} (0600)", fg=typer.colors.GREEN)
    typer.echo(raw)


@account_app.command("reset-password")
def account_reset_password(
    name: Annotated[str, typer.Option("--name", help="Member name.")] = "owner",
    project: Annotated[str, typer.Option("--project", help="Project key.")] = "RDM",
    password: Annotated[
        str | None, typer.Option("--password", help="New password; random when omitted.")
    ] = None,
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
) -> None:
    """Reset a human member's password offline (stop the server first)."""
    from rdm.interfaces.cli import account as account_commands

    raw = account_commands.reset_password(
        data_dir,
        project_key=project,
        name=name,
        new_password=password,
        password_file=data_dir / "bootstrap-password",
    )
    typer.secho(
        f"password reset for {name!r} in {project}"
        + (" (bootstrap-password updated)" if name == "owner" and project == "RDM" else ""),
        fg=typer.colors.GREEN,
    )
    typer.echo(raw)


@db_app.command("upgrade")
def db_upgrade(
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
    revision: Annotated[str, typer.Argument(help="Target revision, default head.")] = "head",
) -> None:
    """Apply migrations up to REVISION (idempotent)."""
    from rdm.interfaces.cli import db as db_commands

    db_commands.run_upgrade(data_dir, revision)


@db_app.command("downgrade")
def db_downgrade(
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
    revision: Annotated[str, typer.Argument(help="Target revision, e.g. -1 or base.")] = "-1",
) -> None:
    """Roll back migrations to REVISION."""
    from rdm.interfaces.cli import db as db_commands

    db_commands.run_downgrade(data_dir, revision)


@db_app.command("status")
def db_status(data_dir: DataDirOpt = DEFAULT_DATA_DIR) -> None:
    """Show current migration revision and whether the DB is at head."""
    from rdm.interfaces.cli import db as db_commands

    db_commands.run_status(data_dir)


@project_app.command("list")
def project_list(
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
) -> None:
    """List all projects via the HTTP API."""
    from rdm.interfaces.cli import client

    client.run_project_list(url, client.resolve_token(token, data_dir))


@project_app.command("get")
def project_get(
    key: Annotated[str, typer.Argument(help="Project key, e.g. DEMO.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
) -> None:
    """Show one project by key."""
    from rdm.interfaces.cli import client

    client.run_project_get(url, client.resolve_token(token, data_dir), key)


@project_app.command("create")
def project_create(
    key: Annotated[str, typer.Argument(help="2-12 uppercase letters/digits, e.g. DEMO.")],
    name: Annotated[str, typer.Option("--name", help="Display name (Chinese allowed).")],
    description: Annotated[
        str | None, typer.Option("--description", help="Optional markdown description.")
    ] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
) -> None:
    """Create a project (Owner only)."""
    from rdm.interfaces.cli import client

    client.run_project_create(url, client.resolve_token(token, data_dir), key, name, description)


@member_app.command("list")
def member_list(
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
    project: ProjectOpt = None,
) -> None:
    """List project members via the HTTP API."""
    from rdm.interfaces.cli import client

    client.run_member_list(url, client.resolve_token(token, data_dir), project)


@member_app.command("create")
def member_create(
    name: Annotated[str, typer.Argument(help="Member name, unique within the project.")],
    type: Annotated[str, typer.Option("--type", help="human | agent")] = "human",
    manager: Annotated[
        str | None, typer.Option("--manager", help="Manager member id (required for agents).")
    ] = None,
    roles: Annotated[str, typer.Option("--roles", help="Comma-separated roles.")] = "worker",
    accept_kinds: Annotated[
        str | None, typer.Option("--accept-kinds", help="Comma-separated kinds.")
    ] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
    project: ProjectOpt = None,
) -> None:
    """Create a project member via the HTTP API."""
    from rdm.interfaces.cli import client

    client.run_member_create(
        url,
        client.resolve_token(token, data_dir),
        project,
        {
            "name": name,
            "type": type,
            "manager_member_id": manager,
            "roles": [r for r in roles.split(",") if r],
            "accept_kinds": accept_kinds.split(",") if accept_kinds else None,
        },
    )


@token_app.command("issue")
def token_issue(
    member_id: Annotated[str, typer.Argument(help="Member id (ULID).")],
    label: Annotated[str, typer.Option("--label")] = "cli",
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
) -> None:
    """Issue a new token for a member; the plaintext is shown exactly once."""
    from rdm.interfaces.cli import client

    client.run_token_issue(url, client.resolve_token(token, data_dir), member_id, label)


@token_app.command("revoke")
def token_revoke(
    token_id: Annotated[str, typer.Argument(help="Token id (ULID).")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
    data_dir: TokenDataDirOpt = None,
) -> None:
    """Revoke a token."""
    from rdm.interfaces.cli import client

    client.run_token_revoke(url, client.resolve_token(token, data_dir), token_id)


@skills_app.command("install")
def skills_install(
    target: Annotated[
        str,
        typer.Option("--target", help="Target agent CLI: claude | codex | opencode."),
    ],
    scope: Annotated[str, typer.Option("--scope", help="user | project.")] = "user",
    skill: Annotated[
        list[str] | None,
        typer.Option("--skill", help="Skill name to install; repeatable. Default: all."),
    ] = None,
    cwd: Annotated[
        Path | None, typer.Option("--cwd", help="Project scope: directory to install into.")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite conflicting files.")] = False,
) -> None:
    """Install bundled rdm skills into an agent CLI."""
    from rdm.interfaces.cli import skills as skills_commands

    if target not in {t.value for t in skills_commands.SkillTarget}:
        typer.secho(
            f"unknown --target {target!r} (want claude|codex|opencode)", fg=typer.colors.RED
        )
        raise typer.Exit(2)
    if scope not in {"user", "project"}:
        typer.secho(f"unknown --scope {scope!r} (want user|project)", fg=typer.colors.RED)
        raise typer.Exit(2)
    if scope == "project" and cwd is None:
        typer.secho("--scope project requires --cwd", fg=typer.colors.RED)
        raise typer.Exit(2)
    directory = cwd or Path.cwd()

    names = skill or skills_commands.bundled_skill_names()
    had_conflict = False
    for name in names:
        try:
            result = skills_commands.install_skill(
                skills_commands.SkillTarget(target),
                scope,
                name,
                force=force,
                cwd=directory,
            )
        except FileNotFoundError:
            bundled = skills_commands.bundled_skill_names()
            typer.secho(f"unknown skill {name!r}; bundled: {bundled}", fg=typer.colors.RED)
            raise typer.Exit(2) from None
        if result.status == "conflict":
            had_conflict = True
            typer.secho(
                f"CONFLICT {name} -> {result.path} (content differs; rerun with --force)",
                fg=typer.colors.YELLOW,
            )
        else:
            typer.secho(
                f"{result.status.upper():9s} {name} -> {result.path}", fg=typer.colors.GREEN
            )
    if had_conflict:
        raise typer.Exit(2)


@integrate_app.command("mcp")
def integrate_mcp(
    target: Annotated[
        str | None,
        typer.Option("--target", help="claude | codex | opencode. Default: all three."),
    ] = None,
    scope: Annotated[
        str, typer.Option("--scope", help="user (global) | project (this directory).")
    ] = "user",
    url: Annotated[str, typer.Option("--url", help="MCP endpoint URL.")] = (
        "http://127.0.0.1:8765/mcp"
    ),
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite a conflicting rdm entry.")
    ] = False,
    member: Annotated[
        str | None,
        typer.Option("--member", help="Project scope: member name or id to bind."),
    ] = None,
    project: ProjectOpt = None,
    member_token: Annotated[
        str | None,
        typer.Option(
            "--member-token",
            help="Project scope: bind this member token directly instead of issuing one.",
        ),
    ] = None,
    method: Annotated[
        str,
        typer.Option(
            "--method",
            help="oauth (native browser authorization, default) or token (static PAT).",
        ),
    ] = "oauth",
    owner_token: TokenOpt = None,
    cwd: Annotated[
        Path | None, typer.Option("--cwd", help="Project scope: directory to bind.")
    ] = None,
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
) -> None:
    """Generate MCP client configs (user-level) or bind a directory (project)."""
    from rdm.interfaces.cli import integrate as integrate_commands

    if scope not in {"user", "project"}:
        typer.secho(f"unknown --scope {scope!r} (want user|project)", fg=typer.colors.RED)
        raise typer.Exit(2)
    if method not in {"oauth", "token"}:
        typer.secho(f"unknown --method {method!r} (want oauth|token)", fg=typer.colors.RED)
        raise typer.Exit(2)

    if scope == "project":
        _integrate_project_scope(
            target=target,
            cwd=cwd or Path.cwd(),
            url=url,
            force=force,
            member_ref=member,
            project_key=project,
            member_token=member_token,
            method=method,
            owner_token=owner_token,
            data_dir=data_dir,
        )
        return

    if target is not None and target not in {t.value for t in integrate_commands.IntegrateTarget}:
        typer.secho(
            f"unknown --target {target!r} (want claude|codex|opencode)", fg=typer.colors.RED
        )
        raise typer.Exit(2)

    names = [target] if target else [t.value for t in integrate_commands.IntegrateTarget]
    had_conflict = False
    for name in names:
        merger = integrate_commands.MERGERS[integrate_commands.IntegrateTarget(name)]
        try:
            result = merger(Path.home(), url, force=force, method=method)
        except ValueError as exc:
            typer.secho(f"{name}: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from None
        if name == "codex":
            note = "codex config path is inferred"
            if method == "oauth":
                note += " and OAuth support is unverified"
            typer.secho(f"note: {note}", fg=typer.colors.YELLOW)
        if result.status == "conflict":
            had_conflict = True
            typer.secho(
                f"CONFLICT {name}: rdm already configured at {result.path}; rerun with --force",
                fg=typer.colors.YELLOW,
            )
        else:
            typer.secho(
                f"{result.status.upper():7s} {name} -> {result.path}", fg=typer.colors.GREEN
            )

    typer.echo("")
    for note in integrate_commands.post_install_notes(data_dir, method=method):
        typer.echo(f"  {note}")
    if had_conflict:
        raise typer.Exit(2)


def _integrate_project_scope(
    *,
    target: str | None,
    cwd: Path,
    url: str,
    force: bool,
    member_ref: str | None,
    project_key: str | None,
    member_token: str | None,
    method: str,
    owner_token: str | None,
    data_dir: Path,
) -> None:
    from rdm.interfaces.cli import client as http_client
    from rdm.interfaces.cli import integrate as integrate_commands

    names = [target] if target else ["claude", "opencode"]
    if "codex" in names:
        typer.secho(
            "codex has no supported project-level MCP config; use --scope user for codex",
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    # Resolve the member token to bind for the static-token method: explicit
    # --member-token, or issue one with the owner credential. The oauth method
    # writes no secret; identity is chosen in the browser consent page.
    raw_token = member_token or ""
    if method == "token" and not raw_token:
        if not member_ref:
            typer.secho(
                "project scope --method token needs --member <name|id> (or --member-token)",
                fg=typer.colors.RED,
            )
            raise typer.Exit(2)
        owner = http_client.resolve_token(owner_token, data_dir)
        base = url.rstrip("/").removesuffix("/mcp")
        key = project_key or "RDM"
        raw_token = http_client.issue_member_token_by_ref(
            base, owner, key, member_ref, f"project:{cwd.name}"
        )
        typer.secho(
            f"issued token for {member_ref} in project {key}",
            fg=typer.colors.GREEN,
        )

    cwd.mkdir(parents=True, exist_ok=True)
    had_conflict = False
    for name in names:
        try:
            if name == "claude":
                result = integrate_commands.merge_claude_project(
                    Path.home(), cwd, url, raw_token, force=force, method=method
                )
                gitignore = False
            else:
                result, gitignore = integrate_commands.merge_opencode_project(
                    cwd, url, raw_token, force=force, method=method
                )
        except ValueError as exc:
            typer.secho(f"{name}: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from None
        if result.status == "conflict":
            had_conflict = True
            typer.secho(
                f"CONFLICT {name}: {result.path} already binds rdm; rerun with --force",
                fg=typer.colors.YELLOW,
            )
            continue
        typer.secho(f"{result.status.upper():7s} {name} -> {result.path}", fg=typer.colors.GREEN)
        if name == "opencode" and gitignore:
            typer.secho(
                "         added .opencode/opencode.json to .gitignore (contains a token)",
                fg=typer.colors.YELLOW,
            )

    typer.echo("")
    if method == "oauth":
        typer.echo("  restart the agent CLI there; a browser will prompt for login")
        typer.echo("  and member choice on first use (whoami confirms the identity).")
    else:
        typer.echo(f"  directory {cwd} now acts as the bound member in this rdm project.")
        typer.echo("  restart the agent CLI there; whoami confirms member and project.")
    if had_conflict:
        raise typer.Exit(2)


def _validate_target(target: str | None) -> list[str]:
    from rdm.interfaces.cli import integrate as integrate_commands

    names = [target] if target else [t.value for t in integrate_commands.IntegrateTarget]
    invalid = [n for n in names if n not in {t.value for t in integrate_commands.IntegrateTarget}]
    if invalid:
        typer.secho(f"unknown --target {invalid[0]!r}", fg=typer.colors.RED)
        raise typer.Exit(2)
    return names


def _run_uninstall_mcp(names: list[str], cwd: Path | None) -> None:
    from rdm.interfaces.cli import integrate as commands

    project_scope = cwd is not None
    if project_scope and "codex" in names:
        typer.secho(
            "codex has no supported project-level MCP config; use --scope user",
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    directory = cwd or Path.cwd()
    had_anything = False
    for name in names:
        try:
            if project_scope:
                if name == "claude":
                    result = commands.remove_claude_project(Path.home(), directory)
                    gitignore = False
                else:
                    result, gitignore = commands.remove_opencode_project(directory)
            else:
                result = commands.REMOVERS[commands.IntegrateTarget(name)](Path.home())
                gitignore = False
        except ValueError as exc:
            typer.secho(f"{name}: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from None
        if result.status == "removed":
            had_anything = True
            parts = []
            if result.detail:
                parts.append(result.detail)
            if gitignore:
                parts.append("removed .gitignore entry")
            extra = f" ({'; '.join(parts)})" if parts else ""
            typer.secho(f"REMOVED   {name} -> {result.path}{extra}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"ABSENT    {name} (no rdm entry found)", fg=typer.colors.YELLOW)
    if not had_anything:
        typer.secho("nothing to remove", fg=typer.colors.YELLOW)


def _run_uninstall_skills(
    names: list[str], *, scope: str, skill: list[str] | None, cwd: Path | None, force: bool
) -> None:
    from rdm.interfaces.cli import skills as skills_commands

    if scope not in {"user", "project"}:
        typer.secho(f"unknown --scope {scope!r} (want user|project)", fg=typer.colors.RED)
        raise typer.Exit(2)

    skill_names = skill or skills_commands.bundled_skill_names()
    directory = cwd or Path.cwd()
    blocked = False
    for name_target in names:
        for name_skill in skill_names:
            result = skills_commands.uninstall_skill(
                skills_commands.SkillTarget(name_target),
                scope,
                name_skill,
                force=force,
                cwd=directory,
            )
            if result.status == "removed":
                typer.secho(f"REMOVED   {result.skill} -> {result.path}", fg=typer.colors.GREEN)
            elif result.status == "absent":
                typer.secho(f"ABSENT    {result.skill} ({name_target})", fg=typer.colors.YELLOW)
            else:  # unmanaged
                blocked = True
                typer.secho(
                    f"UNMANAGED {result.skill} -> {result.path} "
                    "(not rdm-managed; rerun with --force to delete)",
                    fg=typer.colors.RED,
                )
    if blocked:
        raise typer.Exit(2)


@uninstall_app.command("mcp")
def uninstall_mcp(
    target: Annotated[
        str | None,
        typer.Option("--target", help="claude | codex | opencode. Default: all three."),
    ] = None,
    scope: Annotated[
        str, typer.Option("--scope", help="user (global) | project (a directory).")
    ] = "user",
    cwd: Annotated[
        Path | None,
        typer.Option("--cwd", help="Directory to unbind (required with --scope project)."),
    ] = None,
) -> None:
    """Remove the rdm MCP server entry from agent CLI config(s)."""
    if scope not in {"user", "project"}:
        typer.secho(f"unknown --scope {scope!r} (want user|project)", fg=typer.colors.RED)
        raise typer.Exit(2)
    if scope == "project" and cwd is None:
        typer.secho("--scope project requires --cwd", fg=typer.colors.RED)
        raise typer.Exit(2)
    if scope == "user":
        cwd = None
    _run_uninstall_mcp(_validate_target(target), cwd)


@uninstall_app.command("skills")
def uninstall_skills(
    target: Annotated[
        str | None,
        typer.Option("--target", help="claude | codex | opencode. Default: all three."),
    ] = None,
    scope: Annotated[str, typer.Option("--scope", help="user | project.")] = "user",
    skill: Annotated[
        list[str] | None,
        typer.Option("--skill", help="Skill to remove; repeatable. Default: all bundled."),
    ] = None,
    cwd: Annotated[
        Path | None, typer.Option("--cwd", help="Directory for --scope project.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Remove even a non-rdm-managed file.")
    ] = False,
) -> None:
    """Remove rdm skills installed into an agent CLI."""
    _run_uninstall_skills(_validate_target(target), scope=scope, skill=skill, cwd=cwd, force=force)


@uninstall_app.command("all")
def uninstall_all(
    target: Annotated[
        str | None,
        typer.Option("--target", help="claude | codex | opencode. Default: all three."),
    ] = None,
) -> None:
    """Remove user-scope rdm MCP config and all bundled rdm skills."""
    names = _validate_target(target)
    _run_uninstall_mcp(names, None)
    _run_uninstall_skills(names, scope="user", skill=None, cwd=None, force=False)


@app.command()
def doctor(
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    skip_endpoint: Annotated[
        bool, typer.Option("--skip-endpoint", help="Do not probe the running server")
    ] = False,
) -> None:
    """Run data-dir/database/workflow/outbox/attachment diagnostics."""
    from rdm.config import Settings
    from rdm.interfaces.cli.doctor import run_doctor

    settings = Settings(data_dir=data_dir)
    code = run_doctor(settings, as_json=as_json, include_endpoint=not skip_endpoint)
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
