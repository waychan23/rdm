"""HTTP-client implementations of `rdm` admin commands (§17)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import typer

DEFAULT_PROJECT_KEY = "RDM"


def resolve_token(token: str | None) -> str:
    """A PAT is the only CLI credential; create one in the Web personal settings."""
    if token:
        return token
    typer.secho(
        "no token: pass --token or set RDM_TOKEN. PAT 只能由本人在 Web「个人设置 → 访问令牌」"
        "或 `rdm me token create` 创建（已取消 bootstrap-token）。",
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


def _get(url: str, token: str, path: str) -> Any:
    r = _http.get(f"{url}{path}", headers=_headers(token), timeout=10)
    if r.is_error:
        _fail(r)
    return r.json()["data"]


def _post(url: str, token: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    r = _http.post(f"{url}{path}", headers=_headers(token), json=payload or {}, timeout=10)
    if r.is_error:
        _fail(r)
    return r.json()["data"] if r.content else None


def _patch(url: str, token: str, path: str, payload: dict[str, Any]) -> Any:
    r = _http.patch(f"{url}{path}", headers=_headers(token), json=payload, timeout=10)
    if r.is_error:
        _fail(r)
    return r.json()["data"]


def _delete(url: str, token: str, path: str) -> None:
    r = _http.delete(f"{url}{path}", headers=_headers(token), timeout=10)
    if r.is_error:
        _fail(r)


# --- projects -------------------------------------------------------------


def run_project_list(url: str, token: str) -> None:
    _show(_get(url, token, "/api/v1/projects"))


def run_project_get(url: str, token: str, key: str) -> None:
    _show(_get(url, token, f"/api/v1/projects/{key}"))


def run_project_create(
    url: str, token: str, key: str, name: str, description_md: str | None
) -> None:
    payload: dict[str, Any] = {"key": key, "name": name}
    if description_md is not None:
        payload["description_md"] = description_md
    _show(_post(url, token, "/api/v1/projects", payload))


def run_project_transfer_owner(url: str, token: str, key: str, user_ref: str) -> None:
    user_id = _resolve_user_id(url, token, user_ref)
    _show(_post(url, token, f"/api/v1/projects/{key}/transfer-owner", {"user_id": user_id}))


# --- project members ------------------------------------------------------


def run_member_list(url: str, token: str, project: str | None) -> None:
    key = _project_key(project)
    _show(_get(url, token, f"/api/v1/projects/{key}/members"))


def run_member_add(
    url: str, token: str, project: str | None, user_ref: str, roles: list[str]
) -> None:
    key = _project_key(project)
    user_id = _resolve_user_id(url, token, user_ref)
    _show(
        _post(
            url,
            token,
            f"/api/v1/projects/{key}/members",
            {"user_id": user_id, "roles": roles},
        )
    )


def run_member_roles(
    url: str, token: str, project: str | None, user_ref: str, roles: list[str]
) -> None:
    key = _project_key(project)
    user_id = _resolve_user_id(url, token, user_ref)
    _show(
        _patch(
            url,
            token,
            f"/api/v1/projects/{key}/members/{user_id}",
            {"roles": roles},
        )
    )


def run_member_remove(url: str, token: str, project: str | None, user_ref: str) -> None:
    key = _project_key(project)
    user_id = _resolve_user_id(url, token, user_ref)
    _delete(url, token, f"/api/v1/projects/{key}/members/{user_id}")
    typer.secho(f"removed {user_ref} from {key}", fg=typer.colors.GREEN)


# --- organization users ---------------------------------------------------


def _resolve_user_id(url: str, token: str, user_ref: str) -> str:
    users = _get(url, token, "/api/v1/users")
    match = next((u for u in users if u["id"] == user_ref or u["name"] == user_ref), None)
    if match is None:
        typer.secho(f"user {user_ref!r} not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    return match["id"]


def run_user_list(url: str, token: str, type: str | None) -> None:
    path = "/api/v1/users" + (f"?type={type}" if type else "")
    _show(_get(url, token, path))


def run_user_create(url: str, token: str, name: str, email: str | None) -> None:
    payload: dict[str, Any] = {"name": name}
    if email:
        payload["email"] = email
    data = _post(url, token, "/api/v1/users", payload)
    _show(data)
    typer.secho("把 password_reset_url 复制给该用户（24 小时内有效）", fg=typer.colors.GREEN)


def run_user_reset_link(url: str, token: str, user_ref: str) -> None:
    user_id = _resolve_user_id(url, token, user_ref)
    data = _post(url, token, f"/api/v1/users/{user_id}/password-reset-token")
    _show(data)


def run_user_set_active(url: str, token: str, user_ref: str, *, active: bool) -> None:
    user_id = _resolve_user_id(url, token, user_ref)
    action = "enable" if active else "disable"
    _show(_post(url, token, f"/api/v1/users/{user_id}/{action}"))


def run_user_revoke_tokens(url: str, token: str, user_ref: str) -> None:
    user_id = _resolve_user_id(url, token, user_ref)
    _show(_post(url, token, f"/api/v1/users/{user_id}/tokens/revoke-all"))


def run_user_set_roles(url: str, token: str, user_ref: str, roles: list[str]) -> None:
    user_id = _resolve_user_id(url, token, user_ref)
    url_ = f"{url}/api/v1/users/{user_id}/org-roles"
    r = _http.put(url_, headers=_headers(token), json={"roles": roles}, timeout=10)
    if r.is_error:
        _fail(r)
    _show(r.json()["data"])


def run_org_transfer_owner(url: str, token: str, user_ref: str) -> None:
    user_id = _resolve_user_id(url, token, user_ref)
    _show(_post(url, token, "/api/v1/org/transfer-owner", {"user_id": user_id}))


# --- self-service ---------------------------------------------------------


def run_me_token_list(url: str, token: str) -> None:
    _show(_get(url, token, "/api/v1/me/tokens"))


def run_me_token_create(
    url: str,
    token: str,
    label: str,
    expires_in_days: int | None,
    as_agent: str | None,
) -> None:
    payload: dict[str, Any] = {"label": label}
    if expires_in_days is not None:
        payload["expires_in_days"] = expires_in_days
    if as_agent:
        agents = _get(url, token, "/api/v1/me/agents")
        match = next((a for a in agents if a["id"] == as_agent or a["name"] == as_agent), None)
        if match is None:
            typer.secho(f"agent {as_agent!r} not found", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        payload["act_as_user_id"] = match["id"]
    _show(_post(url, token, "/api/v1/me/tokens", payload))


def run_me_token_revoke(url: str, token: str, token_id: str) -> None:
    _delete(url, token, f"/api/v1/me/tokens/{token_id}")
    typer.secho(f"revoked {token_id}", fg=typer.colors.GREEN)


def run_me_agent_list(url: str, token: str) -> None:
    _show(_get(url, token, "/api/v1/me/agents"))


def run_me_agent_create(url: str, token: str, name: str, accept_kinds: list[str]) -> None:
    _show(
        _post(
            url,
            token,
            "/api/v1/me/agents",
            {"name": name, "accept_kinds": accept_kinds},
        )
    )


def run_me_agent_update(url: str, token: str, agent_ref: str, payload: dict[str, Any]) -> None:
    agents = _get(url, token, "/api/v1/me/agents")
    match = next((a for a in agents if a["id"] == agent_ref or a["name"] == agent_ref), None)
    if match is None:
        typer.secho(f"agent {agent_ref!r} not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    _show(_patch(url, token, f"/api/v1/me/agents/{match['id']}", payload))
