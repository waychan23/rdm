"""Integration tests: REST auth, projects, members, tokens (M0-6 + S1 base)."""

from __future__ import annotations


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_healthz_no_auth(server) -> None:
    client, _settings, _app = server
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["version"]


async def test_request_id_roundtrip(server) -> None:
    client, _settings, _app = server
    r = await client.get("/healthz", headers={"X-Request-ID": "req-xyz"})
    assert r.headers["x-request-id"] == "req-xyz"


async def test_whoami_with_bootstrap_owner(server, owner_token) -> None:
    client, _settings, _app = server
    r = await client.get("/api/v1/whoami", headers=auth(owner_token))
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["member"]["name"] == "owner"
    assert body["member"]["roles"] == ["project_owner"]
    assert body["project"]["key"] == "RDM"


async def test_bad_bearer_rejected(server) -> None:
    client, _settings, _app = server
    r = await client.get("/api/v1/whoami", headers={"Authorization": "Bearer nope"})
    assert r.status_code in (401, 403)
    assert r.json()["error"]["code"] in {"AUTH_INVALID_TOKEN", "FORBIDDEN"}


async def test_loopback_shim_owner_without_token(server) -> None:
    """Token-less requests from loopback act as the owner (§16.33)."""
    client, _settings, _app = server
    r = await client.get("/api/v1/whoami")
    assert r.status_code == 200
    assert r.json()["data"]["member"]["roles"] == ["project_owner"]


async def test_non_loopback_without_token_rejected(server) -> None:
    import httpx
    from httpx import ASGITransport

    _client, _settings, app = server
    transport = ASGITransport(app=app, client=("10.0.0.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ext:
        r = await ext.get("/api/v1/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


async def test_deactivated_member_forbidden(server, owner_token) -> None:
    client, settings, app = server
    members = (await client.get("/api/v1/projects/RDM/members", headers=auth(owner_token))).json()[
        "data"
    ]
    owner_id = members[0]["id"]

    async with app.state.container.uow() as uow:
        member = await uow.members.get(owner_id)
        member.is_active = False
        await uow.members.update(member)
    # Member updates invalidate the auth cache in real service flows.
    app.state.container.authenticator.invalidate(owner_token)

    r = await client.get("/api/v1/whoami", headers=auth(owner_token))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_s1_project_and_agent_member_flow(server, owner_token) -> None:
    client, _settings, _app = server

    # S1: owner creates DEMO project.
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "演示项目"}
    )
    assert r.status_code == 201, r.text
    demo = r.json()["data"]
    assert demo["key"] == "DEMO"

    # duplicate key (case-insensitive) -> PROJECT_KEY_DUPLICATE
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "dup"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PROJECT_KEY_DUPLICATE"

    # invalid key -> VALIDATION_ERROR
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "x", "name": "bad"}
    )
    assert r.status_code == 422

    # add a human TL first
    r = await client.post(
        "/api/v1/projects/DEMO/members",
        headers=auth(owner_token),
        json={"name": "tl", "type": "human", "roles": ["manager"]},
    )
    assert r.status_code == 201, r.text
    tl = r.json()["data"]

    # agent without manager -> rejected
    r = await client.post(
        "/api/v1/projects/DEMO/members",
        headers=auth(owner_token),
        json={"name": "frontend-dev", "type": "agent", "agent_cli": "claude", "roles": ["worker"]},
    )
    assert r.status_code == 422
    assert "manager" in r.json()["error"]["message"]

    # agent with manager -> ok
    r = await client.post(
        "/api/v1/projects/DEMO/members",
        headers=auth(owner_token),
        json={
            "name": "frontend-dev",
            "type": "agent",
            "manager_member_id": tl["id"],
            "agent_cli": "claude",
            "roles": ["worker"],
            "accept_kinds": ["task"],
        },
    )
    assert r.status_code == 201, r.text
    agent = r.json()["data"]
    assert agent["manager_member_id"] == tl["id"]

    members = (await client.get("/api/v1/projects/DEMO/members", headers=auth(owner_token))).json()[
        "data"
    ]
    assert {m["name"] for m in members} == {"tl", "frontend-dev"}

    # issue an agent token; it authenticates; revoke then 401.
    r = await client.post(
        f"/api/v1/members/{agent['id']}/tokens",
        headers=auth(owner_token),
        json={"label": "ci"},
    )
    assert r.status_code == 201
    token_id = r.json()["data"]["id"]
    agent_token = r.json()["data"]["token"]

    r = await client.get("/api/v1/whoami", headers=auth(agent_token))
    assert r.status_code == 200
    assert r.json()["data"]["member"]["name"] == "frontend-dev"

    r = await client.delete(f"/api/v1/tokens/{token_id}", headers=auth(owner_token))
    assert r.status_code == 204
    r = await client.get("/api/v1/whoami", headers=auth(agent_token))
    assert r.status_code == 401


async def test_envelope_is_json_on_errors(server, owner_token) -> None:
    client, _settings, _app = server
    r = await client.get("/api/v1/projects/NOPE", headers=auth(owner_token))
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND" and err["message"] and "details" in err
