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

    # Disabling a project owner is allowed; ownership is retained and the
    # inactive state is surfaced in member listings. Re-enabling restores access.
    r = await client.post(f"/api/v1/users/{worker_id}/disable", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    users = (await client.get("/api/v1/users", headers=auth(owner_token))).json()["data"]
    disabled = next(u for u in users if u["id"] == worker_id)
    assert disabled["is_active"] is False
    rows = (await client.get("/api/v1/projects/OWN/members", headers=auth(owner_token))).json()[
        "data"
    ]
    owner_row = next(row for row in rows if row["id"] == worker_id)
    assert "project_owner" in owner_row["roles"]
    r = await client.post(f"/api/v1/users/{worker_id}/enable", headers=auth(owner_token))
    assert r.status_code == 200, r.text


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


async def test_agent_identity_can_complete_done(server, owner_token) -> None:
    """§17.102: an agent that is a step actor may close DONE itself."""
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
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "WORKFLOW_STEP_REQUIRED"

    r = await client.patch(
        f"/api/v1/work-items/{task['display_id']}",
        headers=auth(agent_pat),
        json={"row_version": 3, "review_content_md": "agent finished implementation"},
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]

    # The assignee agent is a DONE candidate and may execute the review.
    r = await client.post(
        f"/api/v1/work-items/{task['display_id']}/steps/CODE_REVIEW",
        headers=auth(agent_pat),
        json={"row_version": version},
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    assert active is not None
    assert active["executors"][0]["user"]["id"] == agent_id

    r = await client.post(
        f"/api/v1/work-item-steps/{active['id']}/execute",
        headers=auth(agent_pat),
        json={"note_md": "self close"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "DONE"


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


async def test_owner_recovery_rejects_proxied_loopback_requests(server) -> None:
    """A reverse proxy connects from loopback; proxy headers must disqualify it."""
    _client, _settings, app = server
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as proxied:
        r = await proxied.post(
            "/api/v1/local/owner-recovery", headers={"X-Forwarded-For": "203.0.113.9"}
        )
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


async def test_user_display_name(server, owner_token) -> None:
    """§17.116: display_name is presentation-only; name stays the address handle."""
    client, _settings, app = server
    await ensure_owner_access(client, app)

    r = await client.post(
        "/api/v1/users",
        headers=auth(owner_token),
        json={"name": "dn-one", "display_name": "  张三  "},
    )
    assert r.status_code == 201, r.text
    user = r.json()["data"]["user"]
    assert user["name"] == "dn-one"
    assert user["display_name"] == "张三"
    uid = user["id"]

    # Omitted display names stay NULL and readers fall back to the login name.
    other_id = await create_human(client, owner_token, "dn-two")
    users = (await client.get("/api/v1/users", headers=auth(owner_token))).json()["data"]
    by_name = {u["name"]: u for u in users}
    assert by_name["dn-two"]["display_name"] is None

    # user_manager can set and clear it; blank means "unset".
    r = await client.patch(
        f"/api/v1/users/{uid}", headers=auth(owner_token), json={"display_name": "李四"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["display_name"] == "李四"
    r = await client.patch(
        f"/api/v1/users/{uid}", headers=auth(owner_token), json={"display_name": "   "}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["display_name"] is None

    # Length is enforced by the schema.
    r = await client.patch(
        f"/api/v1/users/{uid}",
        headers=auth(owner_token),
        json={"display_name": "x" * 101},
    )
    assert r.status_code == 422

    # Self-service edit; whoami reflects the new display name.
    token = await login_pat(client, "dn-two")
    r = await client.patch(
        f"/api/v1/users/{other_id}", headers=auth(token), json={"display_name": "nope"}
    )
    assert r.status_code == 403
    r = await client.patch("/api/v1/me", headers=auth(token), json={"display_name": "王五"})
    assert r.status_code == 200, r.text
    me = (await client.get("/api/v1/whoami", headers=auth(token))).json()["data"]
    assert me["user"]["name"] == "dn-two"
    assert me["user"]["display_name"] == "王五"

    # Agents get one too, maintained by their manager...
    agent_id = await create_agent(client, owner_token, "dn-agent")
    r = await client.patch(
        f"/api/v1/me/agents/{agent_id}",
        headers=auth(owner_token),
        json={"display_name": "小助手"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "dn-agent"
    assert r.json()["data"]["display_name"] == "小助手"
    # ...but org user administration refuses agent profiles.
    r = await client.patch(
        f"/api/v1/users/{agent_id}",
        headers=auth(owner_token),
        json={"display_name": "nope"},
    )
    assert r.status_code == 422


async def test_notification_webhook_is_private(server, owner_token) -> None:
    """RDM-180: only the user themselves or an agent's manager may read webhooks."""
    client, _settings, app = server
    await ensure_owner_access(client, app)

    await client.post(
        "/api/v1/projects", headers=auth(owner_token), json={"key": "LEAK", "name": "Leak"}
    )
    other_id = await create_human(client, owner_token, "webhook-other")
    await add_to_project(client, owner_token, "LEAK", other_id, ["worker"])
    other_token = await login_pat(client, "webhook-other")

    # A user reads and updates their own webhook through /me.
    r = await client.patch(
        "/api/v1/me",
        headers=auth(other_token),
        json={"notify_webhook": "https://hook.example/secret", "notify_webhook_format": "feishu"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["notify_webhook"] == "https://hook.example/secret"
    me = (await client.get("/api/v1/auth/me", headers=auth(other_token))).json()["data"]
    assert me["notify_webhook"] == "https://hook.example/secret"
    who = (await client.get("/api/v1/whoami", headers=auth(other_token))).json()["data"]
    assert who["user"]["notify_webhook"] == "https://hook.example/secret"

    # A manager reads and sets the webhook of an agent they own.
    agent_id = await create_agent(client, other_token, "hook-agent")
    r = await client.patch(
        f"/api/v1/me/agents/{agent_id}",
        headers=auth(other_token),
        json={"notify_webhook": "https://hook.example/agent"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["notify_webhook"] == "https://hook.example/agent"
    agents = (await client.get("/api/v1/me/agents", headers=auth(other_token))).json()["data"]
    assert [a["notify_webhook"] for a in agents] == ["https://hook.example/agent"]

    # Org user administration and the project member directory never carry
    # webhook fields, not even for the org owner.
    users = (await client.get("/api/v1/users", headers=auth(owner_token))).json()["data"]
    assert users
    for user in users:
        assert "notify_webhook" not in user
        assert "notify_webhook_format" not in user
    rows = (await client.get("/api/v1/projects/LEAK/members", headers=auth(owner_token))).json()[
        "data"
    ]
    assert rows
    for row in rows:
        assert "notify_webhook" not in row
        assert "notify_webhook_format" not in row
        for agent in row.get("agents", []):
            assert "notify_webhook" not in agent["user"]
            assert "notify_webhook_format" not in agent["user"]
