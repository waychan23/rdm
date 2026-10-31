"""Integration: product release (version) lifecycle — architecture §17.121."""

from __future__ import annotations

import httpx

from tests.db import sync_rows

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _item(client: httpx.AsyncClient, token: str, payload: dict, key: str = "DEMO") -> dict:
    r = await client.post(f"{API}/projects/{key}/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _get_item(client: httpx.AsyncClient, token: str, ref: str) -> dict:
    r = await client.get(f"{API}/work-items/{ref}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _finish_story(client: httpx.AsyncClient, token: str, ref: str) -> dict:
    for step in ("START", "SUBMIT_TEST", "PASS"):
        item = await _get_item(client, token, ref)
        r = await client.post(
            f"{API}/work-items/{ref}/steps/{step}",
            json={"row_version": item["row_version"]},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text
    item = await _get_item(client, token, ref)
    assert item["status"] == "DONE", item
    return item


async def _release(client: httpx.AsyncClient, token: str, **payload) -> dict:
    r = await client.post(f"{API}/projects/DEMO/releases", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _user_token(client: httpx.AsyncClient, owner: str, name: str, roles: list[str]) -> str:
    from tests.support import make_member

    return (await make_member(client, owner, "DEMO", name, roles))[1]


async def test_release_lifecycle_publish_and_events(server, owner_token: str) -> None:
    client, settings, _app = server
    await _project(client, owner_token)
    story = await _item(client, owner_token, {"kind": "story", "title": "登录", "assignee": "me"})

    release = await _release(
        client,
        owner_token,
        name="v1.0.0",
        description_md="首个版本",
        target_date="2026-11-15",
    )
    assert release["status"] == "PLANNED"
    assert release["stats"]["total"] == 0
    rid = release["id"]

    r = await client.post(
        f"{API}/releases/{rid}/items",
        json={"items": [story["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.get(f"{API}/releases/{rid}", headers=auth(owner_token))
    body = r.json()["data"]
    assert [row["display_id"] for row in body["items"]] == [story["display_id"]]
    assert body["stats"] == {
        "total": 1,
        "done": 0,
        "published": 0,
        "cancelled": 0,
        "percent": 0,
    }
    assert body["readiness"]["can_publish"] is False
    assert body["readiness"]["blocking"][0]["display_id"] == story["display_id"]

    # Publishing with an unfinished story is refused and lists the blocker.
    r = await client.post(f"{API}/releases/{rid}/publish", headers=auth(owner_token))
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "RELEASE_NOT_READY"
    assert err["details"]["reason"] == "unfinished"
    assert err["details"]["blocking"][0]["display_id"] == story["display_id"]

    await _finish_story(client, owner_token, story["display_id"])

    r = await client.get(f"{API}/releases/{rid}", headers=auth(owner_token))
    assert r.json()["data"]["readiness"]["can_publish"] is True

    r = await client.post(f"{API}/releases/{rid}/publish", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    published = r.json()
    assert published["data"]["status"] == "RELEASED"
    assert published["data"]["released_at"] is not None
    assert published["meta"]["published"] == [story["id"]]

    # Stories move to PUBLISHED in the same transaction.
    assert (await _get_item(client, owner_token, story["display_id"]))["status"] == "PUBLISHED"

    r = await client.get(f"{API}/releases/{rid}", headers=auth(owner_token))
    body = r.json()["data"]
    assert body["stats"]["done"] == 1
    assert body["stats"]["published"] == 1
    assert body["stats"]["percent"] == 100
    assert body["readiness"]["can_publish"] is False  # terminal releases are frozen

    # Frozen after release: fields and scope are immutable.
    r = await client.patch(
        f"{API}/releases/{rid}", json={"name": "v1.0.1"}, headers=auth(owner_token)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["status"] == "RELEASED"
    fresh = await _item(
        client, owner_token, {"kind": "story", "title": "下个版本", "assignee": "me"}
    )
    r = await client.post(
        f"{API}/releases/{rid}/items",
        json={"items": [fresh["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["status"] == "RELEASED"

    types = {
        row[0]
        for row in sync_rows(
            settings, "select distinct event_type from event where aggregate_type='release'"
        )
    }
    assert {"release.created", "release.item_added", "release.published"} <= types


async def test_release_name_is_unique_per_project(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    await _release(client, owner_token, name="v1")
    r = await client.post(
        f"{API}/projects/DEMO/releases", json={"name": "v1"}, headers=auth(owner_token)
    )
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "RELEASE_NAME_DUPLICATE"
    assert err["details"]["name"] == "v1"

    await _release(client, owner_token, name="v2")
    r = await client.get(
        f"{API}/projects/DEMO/releases", params={"status": "planned"}, headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    assert {row["name"] for row in r.json()["data"]} == {"v1", "v2"}
    r = await client.get(
        f"{API}/projects/DEMO/releases", params={"status": "nope"}, headers=auth(owner_token)
    )
    assert r.status_code == 422, r.text


async def test_release_only_accepts_open_stories_and_allows_multiple_releases(
    server, owner_token: str
) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    epic = await _item(client, owner_token, {"kind": "epic", "title": "e"})
    story = await _item(client, owner_token, {"kind": "story", "title": "s", "assignee": "me"})
    r1 = await _release(client, owner_token, name="v1")
    r2 = await _release(client, owner_token, name="v2")

    r = await client.post(
        f"{API}/releases/{r1['id']}/items",
        json={"items": [epic["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["kind"] == "epic"

    # Done stories are valid release scope; cancellation is not.
    await _finish_story(client, owner_token, story["display_id"])
    r = await client.post(
        f"{API}/releases/{r1['id']}/items",
        json={"items": [story["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    other = await _item(
        client, owner_token, {"kind": "story", "title": "cancelled", "assignee": "me"}
    )
    item = await _get_item(client, owner_token, other["display_id"])
    r = await client.post(
        f"{API}/work-items/{other['display_id']}/transition",
        json={"to": "CANCELLED", "row_version": item["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{API}/releases/{r1['id']}/items",
        json={"items": [other["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["status"] == "CANCELLED"

    # A story may be planned into several releases (Jira-style fix versions).
    r = await client.post(
        f"{API}/releases/{r2['id']}/items",
        json={"items": [story["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    # Adding twice to the same release is rejected.
    r = await client.post(
        f"{API}/releases/{r2['id']}/items",
        json={"items": [story["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["release_id"] == r2["id"]


async def test_release_cancel_permissions_and_empty_publish(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    worker = await _user_token(client, owner_token, "dev", ["worker"])

    r = await client.post(
        f"{API}/projects/DEMO/releases", json={"name": "v1"}, headers=auth(worker)
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

    release = await _release(client, owner_token, name="v1")
    story = await _item(client, owner_token, {"kind": "story", "title": "s", "assignee": "me"})
    r = await client.post(
        f"{API}/releases/{release['id']}/items",
        json={"items": [story["display_id"]]},
        headers=auth(worker),
    )
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/releases/{release['id']}/publish", headers=auth(worker))
    assert r.status_code == 403, r.text

    r = await client.post(f"{API}/releases/{release['id']}/cancel", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "CANCELLED"

    r = await client.post(f"{API}/releases/{release['id']}/publish", headers=auth(owner_token))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["status"] == "CANCELLED"

    empty = await _release(client, owner_token, name="empty")
    r = await client.post(f"{API}/releases/{empty['id']}/publish", headers=auth(owner_token))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["details"]["reason"] == "empty"


async def test_release_publish_is_atomic_when_story_gate_blocks(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    story = await _item(
        client, owner_token, {"kind": "story", "title": "with child", "assignee": "me"}
    )
    await _finish_story(client, owner_token, story["display_id"])
    # A child added after DONE makes the PUBLISHED gate fail.
    await _item(
        client,
        owner_token,
        {"kind": "task", "title": "late child", "parent": story["display_id"]},
    )
    release = await _release(client, owner_token, name="v1")
    r = await client.post(
        f"{API}/releases/{release['id']}/items",
        json={"items": [story["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/releases/{release['id']}/publish", headers=auth(owner_token))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "WORKFLOW_GATE_BLOCKED"

    # The whole publish rolls back: neither the release nor the story moved.
    detail = (await client.get(f"{API}/releases/{release['id']}", headers=auth(owner_token))).json()
    assert detail["data"]["status"] == "PLANNED"
    assert detail["data"]["released_at"] is None
    assert (await _get_item(client, owner_token, story["display_id"]))["status"] == "DONE"
