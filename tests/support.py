"""Identity provisioning helpers for tests (§17 model).

Humans are organization users; project membership is a separate relationship.
Every credential is self-service: tests log a user in through the real OAuth
flow and mint a PAT for that user.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx

from tests.conftest import auth, web_login

PASSWORD = "Passw0rd123"


async def create_human(
    client: httpx.AsyncClient,
    admin_token: str,
    name: str,
    *,
    email: str | None = None,
    password: str = PASSWORD,
) -> str:
    r = await client.post(
        "/api/v1/users", json={"name": name, "email": email}, headers=auth(admin_token)
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    reset_url = data["password_reset_url"]
    ticket = parse_qs(urlparse(reset_url).query)["ticket"][0]
    r = await client.post(
        "/api/v1/auth/set-password",
        json={"ticket": ticket, "new_password": password},
    )
    assert r.status_code == 200, r.text
    return data["user"]["id"]


async def login_pat(
    client: httpx.AsyncClient,
    name: str,
    *,
    password: str = PASSWORD,
    act_as_user_id: str | None = None,
    label: str = "test",
) -> str:
    access, _refresh = await web_login(client, name, password)
    payload: dict = {"label": label}
    if act_as_user_id is not None:
        payload["act_as_user_id"] = act_as_user_id
    r = await client.post("/api/v1/me/tokens", json=payload, headers=auth(access))
    assert r.status_code == 201, r.text
    return r.json()["data"]["token"]


async def add_to_project(
    client: httpx.AsyncClient,
    owner_token: str,
    project: str,
    user_id: str,
    roles: list[str],
) -> dict:
    r = await client.post(
        f"/api/v1/projects/{project}/members",
        json={"user_id": user_id, "roles": roles},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def make_member(
    client: httpx.AsyncClient,
    admin_token: str,
    project: str,
    name: str,
    roles: list[str] | None = None,
    *,
    password: str = PASSWORD,
    act_as_user_id: str | None = None,
) -> tuple[str, str]:
    """Create a human, add it to a project, return (user_id, PAT)."""
    user_id = await create_human(client, admin_token, name, password=password)
    await add_to_project(client, admin_token, project, user_id, roles or ["worker"])
    token = await login_pat(client, name, password=password, act_as_user_id=act_as_user_id)
    return user_id, token


async def create_agent(
    client: httpx.AsyncClient,
    manager_token: str,
    name: str,
    *,
    accept_kinds: list[str] | None = None,
) -> str:
    r = await client.post(
        "/api/v1/me/agents",
        json={"name": name, "accept_kinds": accept_kinds or []},
        headers=auth(manager_token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def create_project(client: httpx.AsyncClient, token: str, key: str) -> None:
    r = await client.post("/api/v1/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text
