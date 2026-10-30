"""`rdm` command-line interface (Typer).

M0 commands: init / serve / db upgrade|downgrade|status / member ...
M1 commands: skills install, integrate mcp. doctor lands in M2.
Admin commands are thin HTTP clients except init/db, which talk to the
database directly (see docs/architecture.md §7).
"""

from pathlib import Path
from typing import Annotated

import typer

from rdm import __version__

DEFAULT_DATA_DIR = Path.home() / "rdm-data"
DEFAULT_URL = "http://127.0.0.1:8765"

DataDirOpt = Annotated[Path, typer.Option("--data-dir", envvar="RDM_DATA_DIR")]
UrlOpt = Annotated[str, typer.Option("--url", envvar="RDM_SERVER_URL")]
TokenOpt = Annotated[str | None, typer.Option("--token", envvar="RDM_TOKEN")]
ProjectOpt = Annotated[str | None, typer.Option("--project", envvar="RDM_PROJECT")]

app = typer.Typer(
    name="rdm",
    help="rd-manager — human/agent collaborative R&D work management.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="Database migration commands (direct DB connection).")
workflow_app = typer.Typer(help="Workflow definition validation.")
account_app = typer.Typer(help="Org-owner recovery through the loopback endpoint.")
project_app = typer.Typer(help="Projects and project membership (API client).")
user_app = typer.Typer(help="Organization user administration (API client).")
me_app = typer.Typer(help="Personal agents and access tokens (API client).")
org_app = typer.Typer(help="Organization-level operations.")
project_members = typer.Typer(help="Project membership.")
skills_app = typer.Typer(help="Install bundled skills into agent CLIs.")
integrate_app = typer.Typer(help="Generate agent integration configs.")
uninstall_app = typer.Typer(
    help="Remove rdm MCP configs and skills from agent CLIs (inverse of install/integrate)."
)

app.add_typer(db_app, name="db")
app.add_typer(workflow_app, name="workflow")
app.add_typer(account_app, name="account")
app.add_typer(project_app, name="project")
project_app.add_typer(project_members, name="members")
app.add_typer(user_app, name="user")
app.add_typer(me_app, name="me")
app.add_typer(org_app, name="org")
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
) -> None:
    """Start the HTTP + MCP server (loopback binds only)."""
    from rdm.interfaces.cli import server as server_commands

    server_commands.run_serve(data_dir, host, port)


@account_app.command("recover-owner")
def account_recover_owner(
    url: UrlOpt = DEFAULT_URL,
) -> None:
    """重新生成 Org Owner 的一次性设置密码链接（需服务在本机运行）。"""
    from rdm.interfaces.cli import account as account_commands

    link = account_commands.recover_owner(url)
    typer.secho("把下面的链接交给 Org Owner（7 天内有效）：", fg=typer.colors.GREEN)
    typer.echo(link)


@workflow_app.command("validate")
def workflow_validate(data_dir: DataDirOpt = DEFAULT_DATA_DIR) -> None:
    """解析 workflow.json5 并检查在途工作项/活动步骤是否仍兼容。"""
    from rdm.interfaces.cli import workflow as workflow_commands

    raise typer.Exit(workflow_commands.validate(data_dir))


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
) -> None:
    """List all projects via the HTTP API."""
    from rdm.interfaces.cli import client

    client.run_project_list(url, client.resolve_token(token))


@project_app.command("get")
def project_get(
    key: Annotated[str, typer.Argument(help="Project key, e.g. DEMO.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Show one project by key."""
    from rdm.interfaces.cli import client

    client.run_project_get(url, client.resolve_token(token), key)


@project_app.command("create")
def project_create(
    key: Annotated[str, typer.Argument(help="2-12 uppercase letters/digits, e.g. DEMO.")],
    name: Annotated[str, typer.Option("--name", help="Display name (Chinese allowed).")],
    description: Annotated[
        str | None, typer.Option("--description", help="Optional markdown description.")
    ] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Create a project (org_owner or project-director)."""
    from rdm.interfaces.cli import client

    client.run_project_create(url, client.resolve_token(token), key, name, description)


@project_app.command("transfer")
def project_transfer(
    key: Annotated[str, typer.Argument(help="Project key.")],
    user: Annotated[str, typer.Option("--user", help="New project owner (name or id).")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """改派项目经理（project-director/Org Owner 或现任 Owner）。"""
    from rdm.interfaces.cli import client

    client.run_project_transfer_owner(url, client.resolve_token(token), key, user)


# --- project members ------------------------------------------------------


@project_members.command("list")
def project_members_list(
    project: ProjectOpt = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """List project members (humans with their agents)."""
    from rdm.interfaces.cli import client

    client.run_member_list(url, client.resolve_token(token), project)


@project_members.command("add")
def project_members_add(
    user: Annotated[str, typer.Option("--user", help="Org user name or id.")],
    roles: Annotated[
        str, typer.Option("--roles", help="Comma-separated project roles.")
    ] = "worker",
    project: ProjectOpt = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Add an org human to the project; their agents join automatically."""
    from rdm.interfaces.cli import client

    client.run_member_add(
        url, client.resolve_token(token), project, user, [r for r in roles.split(",") if r]
    )


@project_members.command("roles")
def project_members_roles(
    user: Annotated[str, typer.Option("--user", help="Org user name or id.")],
    roles: Annotated[str, typer.Option("--roles", help="Comma-separated project roles.")],
    project: ProjectOpt = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Replace a human's project roles."""
    from rdm.interfaces.cli import client

    client.run_member_roles(
        url, client.resolve_token(token), project, user, [r for r in roles.split(",") if r]
    )


@project_members.command("remove")
def project_members_remove(
    user: Annotated[str, typer.Option("--user", help="Org user name or id.")],
    project: ProjectOpt = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Remove a human from the project; their agents leave too."""
    from rdm.interfaces.cli import client

    client.run_member_remove(url, client.resolve_token(token), project, user)


# --- organization users ---------------------------------------------------


@user_app.command("list")
def user_list(
    type: Annotated[str | None, typer.Option("--type", help="human | agent")] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """List organization users (requires user-manager/Org Owner)."""
    from rdm.interfaces.cli import client

    client.run_user_list(url, client.resolve_token(token), type)


@user_app.command("create")
def user_create(
    name: Annotated[str, typer.Argument(help="Login name (unique in the organization).")],
    email: Annotated[str | None, typer.Option("--email")] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Create a human user and print the one-shot password-reset link."""
    from rdm.interfaces.cli import client

    client.run_user_create(url, client.resolve_token(token), name, email)


@user_app.command("reset-password")
def user_reset_password(
    user: Annotated[str, typer.Argument(help="User name or id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Generate a password-reset link (copy it to the account holder)."""
    from rdm.interfaces.cli import client

    client.run_user_reset_link(url, client.resolve_token(token), user)


@user_app.command("disable")
def user_disable(
    user: Annotated[str, typer.Argument(help="User name or id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Disable a human (their agents stop receiving work; tokens are revoked)."""
    from rdm.interfaces.cli import client

    client.run_user_set_active(url, client.resolve_token(token), user, active=False)


@user_app.command("enable")
def user_enable(
    user: Annotated[str, typer.Argument(help="User name or id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Re-enable a human."""
    from rdm.interfaces.cli import client

    client.run_user_set_active(url, client.resolve_token(token), user, active=True)


@user_app.command("revoke-tokens")
def user_revoke_tokens(
    user: Annotated[str, typer.Argument(help="User name or id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Revoke every PAT/family of a user (and agents acting as them)."""
    from rdm.interfaces.cli import client

    client.run_user_revoke_tokens(url, client.resolve_token(token), user)


@user_app.command("roles")
def user_roles(
    user: Annotated[str, typer.Argument(help="User name or id.")],
    roles: Annotated[
        str, typer.Option("--roles", help="Comma-separated: user-manager,project-director")
    ] = "",
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Set organization roles (Org Owner only)."""
    from rdm.interfaces.cli import client

    client.run_user_set_roles(
        url, client.resolve_token(token), user, [r for r in roles.split(",") if r]
    )


@org_app.command("transfer-owner")
def org_transfer_owner(
    user: Annotated[str, typer.Argument(help="New Org Owner (name or id).")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Transfer the single Org Owner role to another active human."""
    from rdm.interfaces.cli import client

    client.run_org_transfer_owner(url, client.resolve_token(token), user)


# --- self-service ---------------------------------------------------------


@me_app.command("tokens")
def me_tokens(
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """List my personal access tokens."""
    from rdm.interfaces.cli import client

    client.run_me_token_list(url, client.resolve_token(token))


@me_app.command("token-create")
def me_token_create(
    label: Annotated[str, typer.Option("--label")] = "cli",
    expires_in_days: Annotated[int | None, typer.Option("--expires-in-days")] = None,
    as_agent: Annotated[
        str | None, typer.Option("--as-agent", help="Act as one of my agents (name or id).")
    ] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Create a PAT for myself (optionally acting as one of my agents)."""
    from rdm.interfaces.cli import client

    client.run_me_token_create(url, client.resolve_token(token), label, expires_in_days, as_agent)


@me_app.command("token-revoke")
def me_token_revoke(
    token_id: Annotated[str, typer.Argument(help="Token id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Revoke one of my PATs."""
    from rdm.interfaces.cli import client

    client.run_me_token_revoke(url, client.resolve_token(token), token_id)


@me_app.command("agents")
def me_agents(
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """List the agents I manage."""
    from rdm.interfaces.cli import client

    client.run_me_agent_list(url, client.resolve_token(token))


@me_app.command("agent-create")
def me_agent_create(
    name: Annotated[str, typer.Argument(help="Agent name (unique in the organization).")],
    accept_kinds: Annotated[
        str | None, typer.Option("--accept-kinds", help="Comma-separated story,issue,task")
    ] = None,
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Create an agent under my account; it joins all my projects."""
    from rdm.interfaces.cli import client

    client.run_me_agent_create(
        url,
        client.resolve_token(token),
        name,
        [k for k in (accept_kinds or "").split(",") if k],
    )


@me_app.command("agent-disable")
def me_agent_disable(
    agent: Annotated[str, typer.Argument(help="Agent name or id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Disable one of my agents (revokes credentials acting as it)."""
    from rdm.interfaces.cli import client

    client.run_me_agent_update(url, client.resolve_token(token), agent, {"is_active": False})


@me_app.command("agent-enable")
def me_agent_enable(
    agent: Annotated[str, typer.Argument(help="Agent name or id.")],
    url: UrlOpt = DEFAULT_URL,
    token: TokenOpt = None,
) -> None:
    """Re-enable one of my agents."""
    from rdm.interfaces.cli import client

    client.run_me_agent_update(url, client.resolve_token(token), agent, {"is_active": True})


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
    data_dir: Path,
) -> None:
    from rdm.interfaces.cli import integrate as integrate_commands

    names = [target] if target else ["claude", "opencode"]
    if "codex" in names:
        typer.secho(
            "codex has no supported project-level MCP config; use --scope user for codex",
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

    # Static-token method: the identity owner must create the PAT themselves
    # (Web "个人设置 → 访问令牌", or `rdm me token-create --as-agent`); no
    # administrator can mint tokens for someone else any more (§17).
    raw_token = member_token or ""
    if method == "token" and not raw_token:
        typer.secho(
            "project scope --method token needs --member-token: create one in the Web "
            "personal settings (or `rdm me token-create [--as-agent]`) and pass it here.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)

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
