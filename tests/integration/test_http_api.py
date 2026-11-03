"""Integration tests: REST auth, projects, members, tokens (M0-6 + S1 base)."""

from __future__ import annotations


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_healthz_no_auth(server) -> None:
    client, _settings, _app = server
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["version"]


async def test_request_id_roundtrip(server) -> None:
    client, _settings, _app = server
    r = await client.get("/api/healthz", headers={"X-Request-ID": "req-xyz"})
    assert r.headers["x-request-id"] == "req-xyz"


async def test_whoami_with_bootstrap_owner(server, owner_token) -> None:
    client, _settings, _app = server
    r = await client.get("/api/v1/whoami", headers=auth(owner_token))
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["user"]["name"] == "owner"
    assert body["org_roles"] == ["org_owner"]
    # No default project is auto-created any more (§17).
    assert body["projects"] == []
    assert body["default_project"] is None


async def test_bad_bearer_rejected(server) -> None:
    client, _settings, _app = server
    r = await client.get("/api/v1/whoami", headers={"Authorization": "Bearer nope"})
    assert r.status_code in (401, 403)
    assert r.json()["error"]["code"] in {"AUTH_INVALID_TOKEN", "FORBIDDEN"}


async def test_no_credentials_rejected_even_from_loopback(server) -> None:
    """The loopback owner shim was removed in M3 (§16.56): every /api call
    needs a Bearer token or a session cookie, loopback included."""
    client, _settings, _app = server
    r = await client.get("/api/v1/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


async def test_non_loopback_without_token_rejected(server) -> None:
    import httpx
    from httpx import ASGITransport

    _client, _settings, app = server
    transport = ASGITransport(app=app, client=("10.0.0.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ext:
        r = await ext.get("/api/v1/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


async def test_deactivated_member_forbidden_immediately(server, owner_token) -> None:
    """Disabling a user takes effect on the very next request; org owners can
    only step down by transferring the role (§17)."""
    from tests.support import add_to_project, create_human, login_pat

    client, _settings, _app = server

    # Owner self-deactivation is refused.
    me = (await client.get("/api/v1/whoami", headers=auth(owner_token))).json()["data"]["user"]
    r = await client.post(f"/api/v1/users/{me['id']}/disable", headers=auth(owner_token))
    assert r.status_code == 403

    await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "演示"}
    )
    temp_id = await create_human(client, owner_token, "temp")
    await add_to_project(client, owner_token, "DEMO", temp_id, ["worker"])
    temp_token = await login_pat(client, "temp")
    assert (await client.get("/api/v1/whoami", headers=auth(temp_token))).status_code == 200

    r = await client.post(f"/api/v1/users/{temp_id}/disable", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/whoami", headers=auth(temp_token))
    # Disabling revokes every credential (401); an already-cached family would
    # surface as 403. Either way access ends immediately.
    assert r.status_code in (401, 403)


async def test_s1_project_and_agent_member_flow(server, owner_token) -> None:
    from tests.support import add_to_project, create_agent, create_human, login_pat

    client, _settings, _app = server

    # S1: org owner creates DEMO project and becomes project owner.
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "演示项目"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["key"] == "DEMO"
    me = (await client.get("/api/v1/whoami", headers=auth(owner_token))).json()["data"]["user"]
    assert r.json()["data"]["owner_user_id"] == me["id"]

    # duplicate key (case-insensitive) and invalid key
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "dup"}
    )
    assert r.status_code == 409
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "x", "name": "bad"}
    )
    assert r.status_code == 422

    # humans are organization users, then added to the project.
    tl_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", tl_id, ["manager"])
    tl_token = await login_pat(client, "tl")

    # agents are created by their manager and follow the human into projects.
    agent_id = await create_agent(client, tl_token, "frontend-dev", accept_kinds=["task"])

    rows = (await client.get("/api/v1/projects/DEMO/members", headers=auth(owner_token))).json()[
        "data"
    ]
    by_name = {row["name"]: row for row in rows}
    assert set(by_name) == {"owner", "tl"}
    agents = by_name["tl"]["agents"]
    assert [a["user"]["id"] for a in agents] == [agent_id]
    assert agents[0]["auto_added"] is True

    # A PAT may act as the agent; whoami shows the agent identity.
    agent_token = await login_pat(client, "tl", act_as_user_id=agent_id)
    r = await client.get("/api/v1/whoami", headers=auth(agent_token))
    assert r.status_code == 200
    assert r.json()["data"]["identity"]["name"] == "frontend-dev"
    assert r.json()["data"]["identity"]["act_as"] is True

    # A user manager may revoke every PAT of a user (including act-as agent
    # tokens) but can never create one on their behalf (§17).
    r = await client.post(f"/api/v1/users/{tl_id}/tokens/revoke-all", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/whoami", headers=auth(agent_token))
    assert r.status_code == 401


async def test_envelope_is_json_on_errors(server, owner_token) -> None:
    client, _settings, _app = server
    r = await client.get("/api/v1/projects/NOPE", headers=auth(owner_token))
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND" and err["message"] and "details" in err
