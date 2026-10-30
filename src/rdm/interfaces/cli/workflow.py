"""`rdm workflow validate`: parse workflow.json5 and check persisted data."""

from __future__ import annotations

from pathlib import Path

import typer

from rdm.config import Settings
from rdm.domain.workflow.loader import load_spec
from rdm.interfaces.cli.doctor import FAIL, check_workflow_data


def validate(data_dir: Path) -> int:
    try:
        spec = load_spec()
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"FAIL workflow.json5 校验失败：{exc}", fg=typer.colors.RED, err=True)
        return 1
    typer.echo(f"version {spec.version} revision {spec.revision}；{len(spec.kinds)} 个 kind")
    result = check_workflow_data(Settings(data_dir=data_dir))
    color = typer.colors.RED if result.status == FAIL else typer.colors.GREEN
    typer.secho(
        f"{result.status} {result.name}: {result.detail}",
        fg=color,
        err=result.status == FAIL,
    )
    return 1 if result.status == FAIL else 0
