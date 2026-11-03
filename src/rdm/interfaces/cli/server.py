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


def _is_local(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback or host in ("localhost",)
    except ValueError:
        return False


def run_serve(
    data_dir: Path,
    host: str,
    port: int,
    database_url: str = "",
    public_base_url: str = "",
) -> None:
    # The v1 --owner-token shared secret was a no-op at runtime; M3 refuses
    # non-loopback binds outright (architecture §16.59). Reach a remote host
    # via SSH port forwarding or an authenticating reverse proxy.
    if not _is_local(host):
        typer.secho(
            "Refusing to bind a non-local address: rdm serves loopback only "
            "(127.0.0.1/localhost/::1). Use SSH port forwarding for remote access.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    settings = Settings(
        data_dir=data_dir,
        host=host,
        port=port,
        **({"database_url": database_url} if database_url else {}),
        **({"public_base_url": public_base_url} if public_base_url else {}),
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
