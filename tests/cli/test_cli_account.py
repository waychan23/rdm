"""Org-owner recovery through the loopback endpoint (§17).

Offline resets and the bootstrap-token file are gone; the CLI can only ask a
running local server for a fresh bootstrap URL.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
from typer.testing import CliRunner

from rdm.interfaces.cli.main import app

runner = CliRunner()


def test_recover_owner_prints_usable_url(live_server) -> None:
    base, _owner_token = live_server
    result = runner.invoke(app, ["account", "recover-owner", "--url", base])
    assert result.exit_code == 0, result.output
    assert "/set-password?ticket=" in result.output

    url = next(line for line in result.output.splitlines() if "/set-password" in line).strip()
    ticket = parse_qs(urlparse(url).query)["ticket"][0]
    with httpx.Client(timeout=10, trust_env=False) as client:
        r = client.post(
            f"{base}/api/v1/auth/set-password",
            json={"ticket": ticket, "new_password": "RecoveredPw123"},
        )
    assert r.status_code == 200, r.text


def test_recover_owner_requires_running_server() -> None:
    result = runner.invoke(app, ["account", "recover-owner", "--url", "http://127.0.0.1:1"])
    assert result.exit_code == 1
    assert "rdm serve" in result.output
