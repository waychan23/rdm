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
    owner_token: str | None,
) -> None:
    if not _is_local(host) and not owner_token:
        typer.secho(
            "Refusing to bind a non-local address without --owner-token (architecture §6).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    settings = Settings(data_dir=data_dir, host=host, port=port, owner_token=owner_token)
    # Migrate first so a bare `rdm serve` on a fresh data dir works.
    from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

    initialize_data_dir(data_dir)
    run_upgrade(data_dir)

    app = create_app(settings)
    typer.secho(f"rdm serving on http://{host}:{port} (data-dir {data_dir})", fg=typer.colors.GREEN)
    uvicorn.run(app, host=host, port=port, log_config=None)
