"""M5 (§17): org roles, agent lifecycle, act-as PAT, remember-me, owner recovery."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy import create_engine, text

from tests.conftest import OWNER_PASSWORD, auth, ensure_owner_access, web_login
from tests.support import add_to_project, create_agent, create_human, login_pat


async def _owner_id(client, owner_token: str) -> str:
    data = (await client.get("/api/v1/whoami", headers=auth(owner_token))).json()["data"]
    return data["user"]["id"]


async def test_org_role_matrix(server, owner_token) -> None:
    client, _settings, app = server
    await ensure_owner_access(client, app)
    owner_id = await _owner_id(client, owner_token)
    await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "D"}
    )
    worker_id = await create_human(client, owner_token, "worker")
    await add_to_project(client, owner_token, "DEMO", worker_id, ["worker"])
    worker = await login_pat(client, "worker")

    # Plain humans cannot administer users or create projects.
    assert (await client.get("/api/v1/users", headers=auth(worker))).status_code == 403
    assert (
        await client.post(
            "/api/v1/projects", headers=auth(worker), json={"key": "NOPE", "name": "n"}
        )
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/users/{worker_id}/disable", headers=auth(worker))
    ).status_code == 403

    # project-director: create project and reassign a project owner.
    r = await client.put(
        f"/api/v1/users/{worker_id}/org-roles",
        headers=auth(owner_token),
        json={"roles": ["project_director"]},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/v1/projects", headers=auth(worker), json={"key": "DIR", "name": "D"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["owner_user_id"] == worker_id
    r = await client.post(
        "/api/v1/projects/DIR/transfer-owner",
        headers=auth(worker),
        json={"user_id": owner_id},
    )
    assert r.status_code == 422  # owner is not a member of DIR
    r = await client.post(
        "/api/v1/projects/DEMO/transfer-owner",
        headers=auth(worker),
        json={"user_id": worker_id},
    )
    assert r.status_code == 200, r.text

    # user-manager: create humans, but cannot create projects or change roles.
    await client.put(
        f"/api/v1/users/{worker_id}/org-roles",
        headers=auth(owner_token),
        json={"roles": ["user_manager"]},
    )
    r = await client.post("/api/v1/users", headers=auth(worker), json={"name": "newbie"})
    assert r.status_code == 201, r.text
    assert "/set-password?ticket=" in r.json()["data"]["password_reset_url"]
    assert (
        await client.post(
            "/api/v1/projects", headers=auth(worker), json={"key": "NOPE2", "name": "n"}
        )
    ).status_code == 403
    r = await client.put(
        f"/api/v1/users/{owner_id}/org-roles", headers=auth(worker), json={"roles": []}
    )
    assert r.status_code == 403


async def test_project_owner_is_single_source_of_truth(server, owner_token) -> None:
    """project.owner_user_id owns the only project_owner role; generic role
    edits cannot grant/revoke it and the owner cannot be removed directly."""
    client, _settings, _app = server
    owner_id = await _owner_id(client, owner_token)
    r = await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "OWN", "name": "Own"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["owner_user_id"] == owner_id

    worker_id = await create_human(client, owner_token, "owner-target")
    # Adding a member can never mint a second owner.
    r = await client.post(
        "/api/v1/projects/OWN/members",
        headers=auth(owner_token),
        json={"user_id": worker_id, "roles": ["project_owner"]},
    )
    assert r.status_code == 422
    await add_to_project(client, owner_token, "OWN", worker_id, ["worker"])

    # Generic role editing cannot grant or revoke project_owner.
    r = await client.patch(
        f"/api/v1/projects/OWN/members/{worker_id}",
        headers=auth(owner_token),
        json={"roles": ["project_owner"]},
    )
    assert r.status_code == 422

    # The owner cannot be removed without transferring first.
    r = await client.delete(f"/api/v1/projects/OWN/members/{owner_id}", headers=auth(owner_token))
    assert r.status_code == 422

    # Transfer moves the field and the mirrored role together.
    r = await client.post(
        "/api/v1/projects/OWN/transfer-owner",
        headers=auth(owner_token),
        json={"user_id": worker_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_user_id"] == worker_id

    rows = (await client.get("/api/v1/projects/OWN/members", headers=auth(owner_token))).json()[
        "data"
    ]
    by_id = {row["id"]: row for row in rows}
    assert "project_owner" not in by_id[owner_id]["roles"]
    assert by_id[worker_id]["roles"].count("project_owner") == 1
    assert sum("project_owner" in row["roles"] for row in rows) == 1

    # The owner keeps the mirrored role through generic edits, even if omitted.
    r = await client.patch(
        f"/api/v1/projects/OWN/members/{worker_id}",
        headers=auth(owner_token),
        json={"roles": ["manager"]},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["roles"]) == {"project_owner", "manager"}
    r = await client.patch(
        f"/api/v1/projects/OWN/members/{worker_id}",
        headers=auth(owner_token),
        json={"roles": []},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["roles"] == ["project_owner"]
    r = await client.delete(f"/api/v1/projects/OWN/members/{worker_id}", headers=auth(owner_token))
    assert r.status_code == 422

    # An active project owner cannot be disabled without transferring first.
    r = await client.post(f"/api/v1/users/{worker_id}/disable", headers=auth(owner_token))
    assert r.status_code == 403


async def test_agent_membership_lifecycle(server, owner_token) -> None:
    client, _settings, _app = server
    await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "D"}
    )
    human_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", human_id, ["manager"])
    manager = await login_pat(client, "tl")
    agent_id = await create_agent(client, manager, "dev")

    rows = (await client.get("/api/v1/projects/DEMO/members", headers=auth(owner_token))).json()[
        "data"
    ]
    tl_row = next(r for r in rows if r["id"] == human_id)
    assert [a["user"]["id"] for a in tl_row["agents"]] == [agent_id]

    # Agents cannot be added or removed directly.
    r = await client.post(
        "/api/v1/projects/DEMO/members",
        headers=auth(owner_token),
        json={"user_id": agent_id, "roles": ["worker"]},
    )
    assert r.status_code == 422
    r = await client.delete(f"/api/v1/projects/DEMO/members/{agent_id}", headers=auth(owner_token))
    assert r.status_code == 422

    # Removing the human cascades; re-adding revives the agent membership.
    assert (
        await client.delete(f"/api/v1/projects/DEMO/members/{human_id}", headers=auth(owner_token))
    ).status_code == 204
    rows = (await client.get("/api/v1/projects/DEMO/members", headers=auth(owner_token))).json()[
        "data"
    ]
    assert all(r["id"] != human_id for r in rows)
    await add_to_project(client, owner_token, "DEMO", human_id, ["worker"])
    rows = (await client.get("/api/v1/projects/DEMO/members", headers=auth(owner_token))).json()[
        "data"
    ]
    tl_row = next(r for r in rows if r["id"] == human_id)
    assert [a["user"]["id"] for a in tl_row["agents"]] == [agent_id]

    # Disabling the human revokes credentials and hides the agent's access.
    agent_pat = await login_pat(client, "tl", act_as_user_id=agent_id)
    assert (await client.get("/api/v1/whoami", headers=auth(agent_pat))).json()["data"]["identity"][
        "name"
    ] == "dev"
    assert (
        await client.post(f"/api/v1/users/{human_id}/disable", headers=auth(owner_token))
    ).status_code == 200
    r = await client.get("/api/v1/whoami", headers=auth(agent_pat))
    assert r.status_code in (401, 403)

    # Re-enable: a fresh act-as PAT works again (old PATs stayed revoked).
    await client.post(f"/api/v1/users/{human_id}/enable", headers=auth(owner_token))
    new_pat = await login_pat(client, "tl", act_as_user_id=agent_id)
    r = await client.get("/api/v1/whoami", headers=auth(new_pat))
    assert r.status_code == 200
    assert r.json()["data"]["identity"]["name"] == "dev"


async def test_agent_identity_cannot_complete_done(server, owner_token) -> None:
    client, _settings, _app = server
    await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "D"}
    )
    human_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", human_id, ["manager"])
    manager = await login_pat(client, "tl")
    agent_id = await create_agent(client, manager, "dev")
    agent_pat = await login_pat(client, "tl", act_as_user_id=agent_id)

    task = (
        await client.post(
            "/api/v1/projects/DEMO/work-items",
            headers=auth(owner_token),
            json={"kind": "task", "title": "t", "task_type": "backend"},
        )
    ).json()["data"]
    r = await client.post(
        f"/api/v1/work-items/{task['display_id']}/assign",
        headers=auth(owner_token),
        json={"member": agent_id},
    )
    assert r.status_code == 200, r.text

    async def move(to: str, version: int) -> httpx.Response:
        return await client.post(
            f"/api/v1/work-items/{task['display_id']}/transition",
            headers=auth(agent_pat),
            json={"to": to, "row_version": version, "reason": "推进"},
        )

    assert (await move("IN_PROGRESS", 1)).status_code == 200
    assert (await move("TO_REVIEW", 2)).status_code == 200
    blocked = await move("DONE", 3)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "FORBIDDEN"

    # The human manager (privileged) can close it.
    human_pat = await login_pat(client, "tl")
    r = await client.post(
        f"/api/v1/work-items/{task['display_id']}/transition",
        headers=auth(human_pat),
        json={"to": "DONE", "row_version": 3, "reason": "验收通过"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("remember,days", [(False, 1), (True, 7)])
async def test_remember_me_lifetime(server, remember: bool, days: int) -> None:
    client, settings, app = server
    await ensure_owner_access(client, app)
    _access, _refresh = await web_login(client, "owner", OWNER_PASSWORD, remember=remember)
    engine = create_engine(settings.db_sync_url)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "select created_at, expires_at, absolute_expires_at, remember "
                "from user_token where kind='oauth_refresh' order by created_at desc limit 1"
            )
        ).one()
    created, expires, absolute, remembered = row
    if isinstance(created, str):
        created = dt.datetime.fromisoformat(created)
        expires = dt.datetime.fromisoformat(expires)
        absolute = dt.datetime.fromisoformat(absolute)
    assert bool(remembered) is remember
    assert abs((expires - created) - dt.timedelta(days=days)) < dt.timedelta(minutes=5)
    assert abs((absolute - created) - dt.timedelta(days=30)) < dt.timedelta(minutes=5)


async def test_owner_recovery_is_loopback_only(server) -> None:
    _client, _settings, app = server
    transport = httpx.ASGITransport(app=app, client=("10.0.0.9", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as external:
        r = await external.post("/api/v1/local/owner-recovery")
    assert r.status_code == 404


async def test_org_owner_transfer_is_unique(server, owner_token) -> None:
    client, _settings, _app = server
    owner_id = await _owner_id(client, owner_token)
    target_id = await create_human(client, owner_token, "bob")

    r = await client.post(
        "/api/v1/org/transfer-owner", headers=auth(owner_token), json={"user_id": target_id}
    )
    assert r.status_code == 200, r.text

    # Only one org owner remains, and the transferred user is the only one.
    bob_token = await login_pat(client, "bob")
    users = (await client.get("/api/v1/users", headers=auth(bob_token))).json()["data"]
    owners = [u for u in users if "org_owner" in u["org_roles"]]
    assert [u["id"] for u in owners] == [target_id]
    me = (await client.get("/api/v1/whoami", headers=auth(owner_token))).json()["data"]
    assert "org_owner" not in me["org_roles"]
    # The former owner cannot transfer the role back without a user-manager grant.
    r = await client.post(
        "/api/v1/org/transfer-owner", headers=auth(owner_token), json={"user_id": owner_id}
    )
    assert r.status_code == 403
