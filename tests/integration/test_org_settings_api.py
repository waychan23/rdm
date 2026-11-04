"""Integration: organization-level Web frontend origin (RDM-127)."""

from __future__ import annotations

import httpx

from tests.support import make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def test_org_web_origin_read_write_and_permissions(server, owner_token: str) -> None:
    client, settings, _app = server
    await _project(client, owner_token)

    # No default value: unset means NULL and the MCP origin is the fallback.
    r = await client.get(f"{API}/org-settings", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["web_origin"] is None
    assert data["default_web_origin"] == settings.base_url

    # A trailing slash is normalized away; path/query/fragment are rejected.
    r = await client.patch(
        f"{API}/org-settings",
        json={"web_origin": "https://rdm.example.com/"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["web_origin"] == "https://rdm.example.com"

    r = await client.get(f"{API}/org-settings", headers=auth(owner_token))
    assert r.json()["data"]["web_origin"] == "https://rdm.example.com"

    for invalid in (
        "https://rdm.example.com/app",
        "https://rdm.example.com?x=1",
        "ftp://rdm.example.com",
        "rdm.example.com",
    ):
        r = await client.patch(
            f"{API}/org-settings", json={"web_origin": invalid}, headers=auth(owner_token)
        )
        assert r.status_code == 422, (invalid, r.text)

    # Explicit null (or empty) clears it.
    r = await client.patch(
        f"{API}/org-settings", json={"web_origin": None}, headers=auth(owner_token)
    )
    assert r.json()["data"]["web_origin"] is None

    # Every member can read it (agents need it); only admins can change it.
    _user_id, worker = await make_member(client, owner_token, "DEMO", "worker")
    r = await client.get(f"{API}/org-settings", headers=auth(worker))
    assert r.status_code == 200, r.text
    r = await client.patch(
        f"{API}/org-settings",
        json={"web_origin": "https://other.example.com"},
        headers=auth(worker),
    )
    assert r.status_code == 403, r.text
