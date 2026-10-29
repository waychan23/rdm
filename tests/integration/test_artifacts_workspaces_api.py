"""Integration: artifacts, workspaces, member PATCH/tokens, sprint PATCH (M2-3)."""

from __future__ import annotations

import sqlite3

import httpx

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str) -> None:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text


async def _member(
    client: httpx.AsyncClient, owner: str, name: str, roles: list[str] | None = None
) -> tuple[str, str]:
    from tests.support import make_member

    return await make_member(client, owner, "DEMO", name, roles or ["worker"])


async def _item(client: httpx.AsyncClient, token: str) -> dict:
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "t", "task_type": "backend"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_artifact_crud_and_owner_types(server, owner_token) -> None:
    client, settings, _app = server
    await _project(client, owner_token)
    item = await _item(client, owner_token)
    worker_id, worker = await _member(client, owner_token, "w")

    # Any same-project member may attach artifacts.
    r = await client.post(
        f"{API}/projects/DEMO/artifacts",
        json={
            "owner_type": "work_item",
            "owner_ref": item["display_id"],
            "kind": "design",
            "label": "Figma",
            "url": "https://figma.example/x",
        },
        headers=auth(worker),
    )
    assert r.status_code == 201, r.text
    art = r.json()["data"]
    assert art["kind"] == "design"

    r = await client.post(
        f"{API}/projects/DEMO/artifacts",
        json={
            "owner_type": "project",
            "owner_ref": "DEMO",
            "kind": "repo",
            "label": "仓库",
            "url": "https://github.com/x/y",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.get(
        f"{API}/projects/DEMO/artifacts",
        params={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(owner_token),
    )
    assert [a["id"] for a in r.json()["data"]] == [art["id"]]

    # Only http(s) URLs accepted.
    r = await client.post(
        f"{API}/projects/DEMO/artifacts",
        json={
            "owner_type": "project",
            "owner_ref": "DEMO",
            "label": "xss",
            "url": "javascript:alert(1)",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    r = await client.post(f"{API}/artifacts/{art['id']}/delete", headers=auth(owner_token))
    assert r.status_code == 204
    with sqlite3.connect(settings.db_path) as conn:
        types = {
            row[0]
            for row in conn.execute(
                "select event_type from event where aggregate_id=?", (art["id"],)
            )
        }
        assert types == {"artifact.added", "artifact.deleted"}
    assert worker_id  # fixture sanity


async def test_workspace_owner_manager_only_crud(server, owner_token) -> None:
    client, settings, _app = server
    await _project(client, owner_token)
    _mgr_id, manager = await _member(client, owner_token, "tl", ["manager"])
    _w_id, worker = await _member(client, owner_token, "dev")

    payload = {
        "name": "主仓",
        "kind": "git_repo",
        "url": "https://github.com/x/y",
        "default_branch": "main",
    }
    r = await client.post(f"{API}/projects/DEMO/workspaces", json=payload, headers=auth(worker))
    assert r.status_code == 403

    r = await client.post(f"{API}/projects/DEMO/workspaces", json=payload, headers=auth(manager))
    assert r.status_code == 201, r.text
    ws = r.json()["data"]

    r = await client.get(f"{API}/projects/DEMO/workspaces", headers=auth(worker))
    assert [w["id"] for w in r.json()["data"]] == [ws["id"]]

    r = await client.patch(
        f"{API}/workspaces/{ws['id']}",
        json={"default_branch": "develop"},
        headers=auth(worker),
    )
    assert r.status_code == 403
    r = await client.patch(
        f"{API}/workspaces/{ws['id']}",
        json={"default_branch": "develop"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert r.json()["data"]["default_branch"] == "develop"

    r = await client.delete(f"{API}/workspaces/{ws['id']}", headers=auth(owner_token))
    assert r.status_code == 204
    with sqlite3.connect(settings.db_path) as conn:
        types = {
            row[0]
            for row in conn.execute(
                "select event_type from event where aggregate_id=?", (ws["id"],)
            )
        }
        assert types == {"workspace.added", "workspace.updated", "workspace.deleted"}


async def test_workspace_location_is_free_form(server, owner_token) -> None:
    """Workspace storage location is optional and free-form (any format)."""
    client, _settings, _app = server
    await _project(client, owner_token)

    locations = ["/mnt/team/repo", "git@github.com:x/y.git", "s3://bucket/path"]
    for index, location in enumerate(locations):
        r = await client.post(
            f"{API}/projects/DEMO/workspaces",
            json={"name": f"ws-{index}", "kind": "other", "url": location},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        ws = r.json()["data"]
        assert ws["url"] == location

        updated = f"{location}-updated"
        r = await client.patch(
            f"{API}/workspaces/{ws['id']}",
            json={"url": updated},
            headers=auth(owner_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["url"] == updated

    # Omitted / whitespace-only are allowed and normalized to "".
    for name, extra in [("omitted", {}), ("blank", {"url": "   "})]:
        r = await client.post(
            f"{API}/projects/DEMO/workspaces",
            json={"name": name, "kind": "other", **extra},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["url"] == ""

    # PATCH can clear an existing location.
    r = await client.post(
        f"{API}/projects/DEMO/workspaces",
        json={"name": "clear-me", "kind": "other", "url": "s3://x/y"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    wid = r.json()["data"]["id"]
    r = await client.patch(
        f"{API}/workspaces/{wid}",
        json={"url": ""},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["url"] == ""


async def test_member_profile_disable_and_token_listing(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    mid, token = await _member(client, owner_token, "agent1", ["worker"])

    # The user edits their own contact settings.
    r = await client.patch(
        f"{API}/me",
        json={"notify_webhook": "https://hook.example", "notify_webhook_format": "feishu"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["notify_webhook"] == "https://hook.example"
    r = await client.patch(
        f"{API}/me", json={"notify_webhook_format": "bogus"}, headers=auth(token)
    )
    assert r.status_code == 422

    # A user lists their own PATs; raw values are never exposed.
    r = await client.get(f"{API}/me/tokens", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1
    assert "token" not in r.json()["data"][0]

    # Administrators disable the user; a worker cannot do it to someone else.
    _wid, worker_token = await _member(client, owner_token, "plainworker", ["worker"])
    r = await client.post(f"{API}/users/{mid}/disable", headers=auth(worker_token))
    assert r.status_code == 403
    r = await client.post(f"{API}/users/{mid}/disable", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.json()["data"]["is_active"] is False


async def test_sprint_patch_and_closed_freeze(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    r = await client.post(
        f"{API}/projects/DEMO/sprints",
        json={"name": "S1", "goal_md": "g"},
        headers=auth(owner_token),
    )
    sid = r.json()["data"]["id"]
    r = await client.patch(
        f"{API}/sprints/{sid}",
        json={"name": "S1'", "end_date": "2026-11-01"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "S1'"

    r = await client.post(f"{API}/sprints/{sid}/start", headers=auth(owner_token))
    assert r.status_code == 200
    r = await client.post(f"{API}/sprints/{sid}/close", headers=auth(owner_token))
    assert r.status_code == 200
    r = await client.patch(
        f"{API}/sprints/{sid}", json={"name": "locked"}, headers=auth(owner_token)
    )
    assert r.status_code == 422
