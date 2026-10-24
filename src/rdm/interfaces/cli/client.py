"""HTTP-client implementations of `rdm member ...` admin commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import typer

DEFAULT_PROJECT_KEY = "RDM"


def resolve_token(token: str | None, data_dir: Path | None) -> str:
    if token:
        return token
    if data_dir is not None:
        bootstrap = data_dir / "bootstrap-token"
        if bootstrap.exists():
            return bootstrap.read_text(encoding="utf-8").strip()
    typer.secho(
        "no token: pass --token, set RDM_TOKEN, or provide --data-dir with bootstrap-token",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=2)


def _project_key(project: str | None) -> str:
    return project or DEFAULT_PROJECT_KEY


def _fail(response: httpx.Response) -> None:
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    typer.secho(json.dumps(body, ensure_ascii=False, indent=2), fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


# The v1 server only binds loopback; never send local admin calls through a
# system/macOS proxy (httpx would otherwise read it via urllib getproxies()).
_http = httpx.Client(timeout=10, trust_env=False)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _show(data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def run_project_list(url: str, token: str) -> None:
    r = _http.get(f"{url}/api/v1/projects", headers=_headers(token), timeout=10)
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_project_get(url: str, token: str, key: str) -> None:
    r = _http.get(f"{url}/api/v1/projects/{key}", headers=_headers(token), timeout=10)
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_project_create(
    url: str, token: str, key: str, name: str, description_md: str | None
) -> None:
    payload: dict[str, Any] = {"key": key, "name": name}
    if description_md is not None:
        payload["description_md"] = description_md
    r = _http.post(
        f"{url}/api/v1/projects",
        headers=_headers(token),
        json=payload,
        timeout=10,
    )
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_member_list(url: str, token: str, project: str | None) -> None:
    key = _project_key(project)
    r = _http.get(f"{url}/api/v1/projects/{key}/members", headers=_headers(token), timeout=10)
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_member_create(url: str, token: str, project: str | None, payload: dict[str, Any]) -> None:
    key = _project_key(project)
    r = _http.post(
        f"{url}/api/v1/projects/{key}/members",
        headers=_headers(token),
        json={k: v for k, v in payload.items() if v is not None},
        timeout=10,
    )
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_token_issue(url: str, token: str, member_id: str, label: str) -> None:
    r = _http.post(
        f"{url}/api/v1/members/{member_id}/tokens",
        headers=_headers(token),
        json={"label": label},
        timeout=10,
    )
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_token_revoke(url: str, token: str, token_id: str) -> None:
    r = _http.delete(f"{url}/api/v1/tokens/{token_id}", headers=_headers(token), timeout=10)
    if r.is_error:
        _fail(r)
    typer.secho(f"revoked {token_id}", fg=typer.colors.GREEN)
