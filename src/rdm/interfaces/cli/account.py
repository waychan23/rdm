"""Owner recovery through the loopback-only HTTP endpoint (§17).

Offline password resets and the bootstrap-token file are gone. The deployer
runs this command on the host that serves the data directory; the server must
be running because only it can mint a bootstrap ticket.
"""

from __future__ import annotations

import json

import httpx
import typer


def recover_owner(url: str) -> str:
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/api/v1/local/owner-recovery",
            timeout=10,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        typer.secho(
            f"无法连接 {url}：{exc}。请先在本机启动 `rdm serve`，再重试。",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    if response.status_code == 404:
        typer.secho(
            "endpoint 拒绝访问：owner-recovery 只接受回环请求（请在部署主机上执行）。",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if response.is_error:
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}
        typer.secho(json.dumps(body, ensure_ascii=False, indent=2), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    data = response.json()["data"]
    return f"{url.rstrip('/')}{data['set_password_url']}"
