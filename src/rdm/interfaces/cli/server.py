"""`rdm serve` implementation."""

from __future__ import annotations

import ipaddress
import logging
from pathlib import Path

import typer
import uvicorn

from rdm.app import create_app
from rdm.config import Settings

logger = logging.getLogger("rdm.serve")


def is_loopback(host: str) -> bool:
    """True for 127.0.0.0/8, ::1 and the literal ``localhost``."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_serve_settings(
    data_dir: Path,
    host: str,
    port: int,
    database_url: str = "",
    public_base_url: str = "",
) -> Settings:
    """Validate bind options without starting the server.

    rdm defaults to loopback, but enterprise deployments may bind a private or
    container address. A non-loopback bind requires an explicit public origin:
    OAuth discovery, ``web_url`` and attachment links all derive from it, and
    an unset origin would otherwise advertise the internal IP over HTTP.
    """
    settings = Settings(
        data_dir=data_dir,
        host=host,
        port=port,
        **({"database_url": database_url} if database_url else {}),
        **({"public_base_url": public_base_url} if public_base_url else {}),
    )
    if not is_loopback(host) and not settings.public_base_url:
        typer.secho(
            "Binding a non-loopback address requires RDM_PUBLIC_BASE_URL "
            "(the HTTPS origin users and MCP clients use). Example: "
            "RDM_PUBLIC_BASE_URL=https://rdm.example.com rdm serve --host 0.0.0.0",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    return settings


def run_serve(
    data_dir: Path,
    host: str,
    port: int,
    database_url: str = "",
    public_base_url: str = "",
) -> None:
    settings = build_serve_settings(data_dir, host, port, database_url, public_base_url)
    if not is_loopback(host):
        # /api/v1/local/* (owner recovery) still rejects non-loopback peers, so
        # this only opens the regular authenticated API. Keep it behind a
        # firewall and an authenticating reverse proxy.
        typer.secho(
            f"Serving on non-loopback host {host}: keep port {port} on a private "
            "network and put TLS/authentication in front of it. "
            "/api/v1/local/* remains loopback-only.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    # Migrate first so a bare `rdm serve` on a fresh data dir works.
    from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

    initialize_data_dir(data_dir)
    run_upgrade(data_dir, database_url=database_url or None)

    # Workflow edits are code changes; a stale active step is not fatal at
    # boot (operators may be mid-upgrade) but must be visible immediately.
    from rdm.interfaces.cli.doctor import FAIL, check_workflow_data

    workflow_check = check_workflow_data(settings)
    if workflow_check.status == FAIL:
        typer.secho(
            f"WARNING workflow-data: {workflow_check.detail}\n"
            "Run `rdm workflow validate` before continuing to serve.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    app = create_app(settings)
    typer.secho(
        f"rdm API on {settings.internal_base_url} (data-dir {data_dir})",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        f"public origin: {settings.base_url} | Web UI: Vite dev server or nginx "
        "(`pnpm -C web-next dev` / deploy/nginx/rdm.conf)",
        fg=typer.colors.GREEN,
    )
    uvicorn.run(app, host=host, port=port, log_config=None)
