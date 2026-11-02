"""`rdm workflow validate`: validate workflow-configs/*.json5 and persisted data."""

from __future__ import annotations

from pathlib import Path

import typer

from rdm.config import Settings
from rdm.domain.workflow.config import parse_config_document
from rdm.domain.workflow.loader import load_spec, load_spec_text
from rdm.interfaces.cli.doctor import FAIL, check_workflow_data


def validate(data_dir: Path, database_url: str | None = None) -> int:
    settings = (
        Settings(data_dir=data_dir, database_url=database_url)
        if database_url
        else Settings(data_dir=data_dir)
    )
    directory = settings.workflow_configs_dir
    paths = sorted(directory.glob("*.json5")) if directory.is_dir() else []

    try:
        if paths:
            documents = [
                (path, parse_config_document(path.read_text(encoding="utf-8"))) for path in paths
            ]
        else:
            documents = [
                (
                    directory / "(packaged default)",
                    parse_config_document(load_spec_text()),
                )
            ]
    except Exception as exc:  # noqa: BLE001 - CLI reports the first failure
        typer.secho(f"FAIL workflow-configs 校验失败：{exc}", fg=typer.colors.RED, err=True)
        return 1

    for path, document in documents:
        summary = (
            f"{path.name}: key {document.key} ({document.name}) "
            f"version {document.schema_version} revision {document.revision}；"
            f"{len(document.spec.kinds)} 个 kind"
        )
        if document.spec.workflow_defs:
            summary += f"，{len(document.spec.workflow_defs)} 个命名定义"
        typer.echo(summary)

    # The packaged default must always be loadable: it is the fallback for
    # projects that have not selected a config version.
    load_spec()
    result = check_workflow_data(settings)
    color = typer.colors.RED if result.status == FAIL else typer.colors.GREEN
    typer.secho(
        f"{result.status} {result.name}: {result.detail}",
        fg=color,
        err=result.status == FAIL,
    )
    return 1 if result.status == FAIL else 0
