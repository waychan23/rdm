"""CLI smoke tests: version/init/db and HTTP-backed member commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rdm.interfaces.cli.main import app


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_init_upgrade_status_idempotent(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert (data_dir / "rdm.db").exists()
    assert (data_dir / "projects").is_dir()

    # second upgrade is a no-op and still succeeds
    result = runner.invoke(app, ["db", "upgrade", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["db", "status", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "0003" in result.output
    assert "up to date" in result.output


def test_serve_refuses_nonlocal_without_owner_token(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "serve",
            "--data-dir",
            str(tmp_path / "data"),
            "--host",
            "0.0.0.0",
        ],
    )
    assert result.exit_code == 2


def test_project_create_get_list_via_cli(live_server) -> None:
    url, token = live_server
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["project", "create", "DEMO", "--name", "演示项目", "--url", url, "--token", token],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["key"] == "DEMO"

    result = runner.invoke(app, ["project", "get", "DEMO", "--url", url, "--token", token])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["name"] == "演示项目"

    result = runner.invoke(app, ["project", "list", "--url", url, "--token", token])
    keys = {p["key"] for p in json.loads(result.output)}
    assert {"RDM", "DEMO"} <= keys

    # duplicate key surfaces PROJECT_KEY_DUPLICATE
    result = runner.invoke(
        app,
        ["project", "create", "DEMO", "--name", "dup", "--url", url, "--token", token],
    )
    assert result.exit_code == 1
    assert "PROJECT_KEY_DUPLICATE" in result.output


def test_member_list_and_create_via_cli(live_server) -> None:
    url, token = live_server
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "member",
            "create",
            "pm",
            "--type",
            "human",
            "--roles",
            "manager",
            "--url",
            url,
            "--token",
            token,
        ],
    )
    assert result.exit_code == 0, result.output
    created = json.loads(result.output)
    assert created["name"] == "pm"

    result = runner.invoke(app, ["member", "list", "--url", url, "--token", token])
    assert result.exit_code == 0, result.output
    names = {m["name"] for m in json.loads(result.output)}
    assert {"owner", "pm"} <= names


def test_member_commands_fail_without_token(live_server) -> None:
    url, _token = live_server
    result = CliRunner().invoke(app, ["member", "list", "--url", url, "--token", "bad-token"])
    assert result.exit_code == 1
    assert "AUTH_INVALID_TOKEN" in result.output
