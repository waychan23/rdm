"""Offline account recovery commands: bootstrap-token rotation and reset-password."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from typer.testing import CliRunner

from rdm.app import create_app
from rdm.config import Settings
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade
from rdm.interfaces.cli.main import app

runner = CliRunner()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live(tmp_path: Path) -> Iterator[tuple[str, str, Path]]:
    data_dir = tmp_path / "data"
    initialize_data_dir(data_dir)
    run_upgrade(data_dir)
    settings = Settings(data_dir=data_dir)
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=_free_port(), log_config=None)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    token = settings.bootstrap_token_path.read_text(encoding="utf-8").strip()
    try:
        yield f"http://127.0.0.1:{server.config.port}", token, data_dir
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _whoami(url: str, token: str) -> int:
    return httpx.get(
        f"{url}/api/v1/whoami",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    ).status_code


def _login(url: str, password: str) -> httpx.Response:
    return httpx.post(
        f"{url}/api/v1/auth/login",
        json={"project_key": "RDM", "name": "owner", "password": password},
        timeout=10,
    )


def test_bootstrap_token_rotation_revokes_old(live) -> None:
    url, old_token, data_dir = live
    assert _whoami(url, old_token) == 200

    result = runner.invoke(app, ["bootstrap-token", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    new_token = (data_dir / "bootstrap-token").read_text(encoding="utf-8").strip()
    assert new_token in result.output
    assert new_token != old_token

    assert _whoami(url, new_token) == 200
    # Prior bootstrap PATs are revoked in the DB. The offline command is meant
    # to run against a stopped server; a live process may still serve a cached
    # token for up to 60s, so assert persistence rather than the live 401.
    import sqlite3

    with sqlite3.connect(data_dir / "rdm.db") as conn:
        live_bootstrap = conn.execute(
            "select count(*) from member_token "
            "where label='bootstrap' and kind='pat' and revoked_at is null"
        ).fetchone()[0]
    assert live_bootstrap == 1


def test_bootstrap_token_keep_old(live) -> None:
    url, old_token, data_dir = live
    result = runner.invoke(app, ["bootstrap-token", "--data-dir", str(data_dir), "--keep-old"])
    assert result.exit_code == 0, result.output
    new_token = (data_dir / "bootstrap-token").read_text(encoding="utf-8").strip()
    assert _whoami(url, new_token) == 200
    assert _whoami(url, old_token) == 200


def test_account_reset_password_updates_file_and_login(live) -> None:
    url, _token, data_dir = live
    old_password = (data_dir / "bootstrap-password").read_text(encoding="utf-8").strip()

    result = runner.invoke(app, ["account", "reset-password", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    new_password = (data_dir / "bootstrap-password").read_text(encoding="utf-8").strip()
    assert new_password in result.output
    assert new_password != old_password

    assert _login(url, old_password).status_code == 401
    r = _login(url, new_password)
    assert r.status_code == 200, r.text
    cookie = {"rdm_session": r.cookies["rdm_session"]}
    assert httpx.get(f"{url}/api/v1/auth/me", cookies=cookie, timeout=10).status_code == 200


def test_account_reset_unknown_member_exits_nonzero(live) -> None:
    _url, _token, data_dir = live
    result = runner.invoke(
        app,
        ["account", "reset-password", "--name", "ghost", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 1
