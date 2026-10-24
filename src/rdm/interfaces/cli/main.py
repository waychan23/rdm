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
TokenDataDirOpt = Annotated[Path | None, typer.Option("--data-dir", envvar="RDM_DATA_DIR")]
ProjectOpt = Annotated[str | None, typer.Option("--project", envvar="RDM_PROJECT")]

app = typer.Typer(
    name="rdm",
    help="rd-manager — human/agent collaborative R&D work management.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="Database migration commands (direct DB connection).")
project_app = typer.Typer(help="List or create projects (API client).")
member_app = typer.Typer(help="Manage project members and tokens (API client).")
token_app = typer.Typer(help="Issue or revoke member tokens.")
skills_app = typer.Typer(help="Install bundled skills into agent CLIs.")
integrate_app = typer.Typer(help="Generate agent integration configs.")

app.add_typer(db_app, name="db")
app.add_typer(project_app, name="project")
app.add_typer(member_app, name="member")
member_app.add_typer(token_app, name="token")
app.add_typer(skills_app, name="skills")
app.add_typer(integrate_app, name="integrate")


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
    owner_token: Annotated[
        str | None,
        typer.Option(
            "--owner-token", envvar="RDM_OWNER_TOKEN", help="Required for non-local bind."
        ),
    ] = None,
) -> None:
    """Start the HTTP + MCP server."""
    from rdm.interfaces.cli import server as server_commands

    server_commands.run_serve(data_dir, host, port, owner_token)


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
    agent_cli: Annotated[
        str | None, typer.Option("--agent-cli", help="claude | codex | opencode | other")
    ] = None,
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
            "agent_cli": agent_cli,
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

    if target == "codex":
        typer.secho(
            "note: codex target path (~/.codex/prompts) is inferred and unverified",
            fg=typer.colors.YELLOW,
        )

    names = skill or skills_commands.bundled_skill_names()
    had_conflict = False
    for name in names:
        try:
            result = skills_commands.install_skill(
                skills_commands.SkillTarget(target), scope, name, force=force
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
    url: Annotated[str, typer.Option("--url", help="MCP endpoint URL.")] = (
        "http://127.0.0.1:8765/mcp"
    ),
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite a conflicting rdm entry.")
    ] = False,
    data_dir: DataDirOpt = DEFAULT_DATA_DIR,
) -> None:
    """Generate user-level MCP client configs for claude/codex/opencode."""
    from rdm.interfaces.cli import integrate as integrate_commands

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
            result = merger(Path.home(), url, force=force)
        except ValueError as exc:
            typer.secho(f"{name}: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from None
        if name == "codex":
            typer.secho(
                "note: codex config path is inferred and unverified", fg=typer.colors.YELLOW
            )
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
    for note in integrate_commands.post_install_notes(data_dir):
        typer.echo(f"  {note}")
    if had_conflict:
        raise typer.Exit(2)


@app.command()
def doctor() -> None:
    """Run environment/database diagnostics (M2)."""
    typer.echo("doctor is implemented in M2")


if __name__ == "__main__":
    app()
