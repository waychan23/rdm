"""Workflow upgrade for pinned work items (RDM-147).

Covers the read-only assessment in ``GET /work-items/{ref}``, the upgrade
write path, the item-level config snapshot and the append-only history entry.
"""

from __future__ import annotations

import json

import httpx
import pyjson5

from rdm.domain.workflow.loader import load_spec_text
from rdm.infrastructure.db.workflow_version_sync import sync_workflow_versions
from tests.db import sync_execute

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _config_text(
    *,
    key: str,
    name: str,
    story_label: str | None = None,
    shrink_story: bool = False,
) -> str:
    raw = pyjson5.loads(load_spec_text())
    raw["key"] = key
    raw["name"] = name
    story = raw["kinds"]["story"]
    if story_label is not None:
        story["label"] = story_label
    if shrink_story:
        story.pop("child_triggers", None)
        story["states"] = ["NEW", "DONE", "CANCELLED"]
        story["initial"] = "NEW"
        story["terminal"] = ["DONE", "CANCELLED"]
        story["main_terminal"] = ["DONE"]
        story["side_terminal"] = ["CANCELLED"]
        story["steps"] = {
            "NEW": [{"key": "FINISH", "name": "完成", "to": "DONE"}],
            "DONE": [],
            "CANCELLED": [],
        }
        story["gates"] = {}
    return json.dumps(raw, ensure_ascii=False)


async def _fork(client: httpx.AsyncClient, token: str, source: str, key: str, name: str) -> dict:
    r = await client.post(
        f"{API}/workflow-configs/{source}/fork",
        json={"key": key, "name": name},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _save(
    client: httpx.AsyncClient,
    token: str,
    key: str,
    *,
    content_text: str,
    base_version_id: str,
) -> dict:
    r = await client.post(
        f"{API}/workflow-configs/{key}/versions",
        json={"content_text": content_text, "base_version_id": base_version_id},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["version"]


async def _create_project(
    client: httpx.AsyncClient, token: str, key: str, version_id: str | None
) -> None:
    body = {"key": key, "name": key}
    if version_id is not None:
        body["workflow_config_version_id"] = version_id
    r = await client.post(f"{API}/projects", json=body, headers=auth(token))
    assert r.status_code == 201, r.text


async def _switch_project(client: httpx.AsyncClient, token: str, key: str, version_id: str) -> None:
    r = await client.patch(
        f"{API}/projects/{key}",
        json={"workflow_config_version_id": version_id},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text


async def _create_story(client: httpx.AsyncClient, token: str, project: str) -> dict:
    r = await client.post(
        f"{API}/projects/{project}/work-items",
        json={"kind": "story", "title": "upgrade me"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _detail(client: httpx.AsyncClient, token: str, display_id: str) -> dict:
    r = await client.get(f"{API}/work-items/{display_id}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def test_new_item_records_workflow_config_snapshot(server, owner_token: str) -> None:
    client, _settings, _app = server
    config = await _fork(client, owner_token, "default", "snap_flow", "Snapshot Flow")
    version = config["version"]
    await _create_project(client, owner_token, "SNAP", version["id"])
    item = await _create_story(client, owner_token, "SNAP")

    assert item["workflow_config_key"] == "snap_flow"
    assert item["workflow_config_version"] == 1
    assert item["workflow_config_version_id"] == version["id"]

    detail = await _detail(client, owner_token, item["display_id"])
    upgrade = detail["meta"]["workflow_upgrade"]
    assert upgrade["available"] is False
    assert upgrade["blockers"] == []
    assert upgrade["current"]["config_key"] == "snap_flow"
    assert upgrade["current"]["config_version"] == 1
    assert upgrade["current"]["def_version"] == item["workflow_version"]

    # A project without an explicit selection falls back to the builtin
    # default config, so the drawer still has a human-readable key.
    await _create_project(client, owner_token, "PLAIN", None)
    plain = await _create_story(client, owner_token, "PLAIN")
    assert plain["workflow_config_key"] == "default"
    assert plain["workflow_config_version"] is not None


async def test_legacy_item_config_snapshot_is_backfilled(server, owner_token: str) -> None:
    client, settings, _app = server
    config = await _fork(client, owner_token, "default", "legacy_flow", "Legacy Flow")
    await _create_project(client, owner_token, "LGCY", config["version"]["id"])
    item = await _create_story(client, owner_token, "LGCY")

    # Simulate a row created before RDM-147 (no config provenance).
    sync_execute(
        settings,
        "update work_item set workflow_config_key = null, "
        "workflow_config_version = null, workflow_config_version_id = null "
        "where id = :id",
        {"id": item["id"]},
    )
    before = await _detail(client, owner_token, item["display_id"])
    assert before["data"]["workflow_config_key"] is None

    report = sync_workflow_versions(settings)
    assert report.config_snapshots >= 1

    after = await _detail(client, owner_token, item["display_id"])
    assert after["data"]["workflow_config_key"] == "legacy_flow"
    assert after["data"]["workflow_config_version"] == 1
    assert after["data"]["workflow_config_version_id"] == config["version"]["id"]


async def test_pre_config_item_backfills_default_key(server, owner_token: str) -> None:
    client, settings, _app = server
    await _create_project(client, owner_token, "PRE", None)
    item = await _create_story(client, owner_token, "PRE")

    # Simulate an item pinned before workflow configs were imported: no
    # provenance and an older definition schema.
    sync_execute(
        settings,
        "update work_item set workflow_config_key = null, "
        "workflow_config_version = null, workflow_config_version_id = null "
        "where id = :id",
        {"id": item["id"]},
    )
    sync_execute(
        settings,
        "update work_item_workflow_version set config_schema_version = 3 where id = :id",
        {"id": item["workflow_def_id"]},
    )

    report = sync_workflow_versions(settings)
    assert report.config_snapshots >= 1

    after = await _detail(client, owner_token, item["display_id"])
    assert after["data"]["workflow_config_key"] == "default"
    assert after["data"]["workflow_config_version"] is None
    assert after["data"]["workflow_config_version_id"] is None


async def test_upgrade_repins_definition_and_records_history(server, owner_token: str) -> None:
    client, _settings, _app = server
    config = await _fork(client, owner_token, "default", "up_flow", "Upgrade Flow")
    await _create_project(client, owner_token, "UPGD", config["version"]["id"])
    item = await _create_story(client, owner_token, "UPGD")
    assert item["status"] == "TODO"

    # A label change is enough to produce a new effective definition.
    new_version = await _save(
        client,
        owner_token,
        "up_flow",
        content_text=_config_text(key="up_flow", name="Upgrade Flow", story_label="需求 v2"),
        base_version_id=config["version"]["id"],
    )
    await _switch_project(client, owner_token, "UPGD", new_version["id"])

    detail = await _detail(client, owner_token, item["display_id"])
    upgrade = detail["meta"]["workflow_upgrade"]
    assert upgrade["available"] is True
    assert upgrade["blockers"] == []
    assert upgrade["target"]["config_key"] == "up_flow"
    assert upgrade["target"]["config_version"] == 2
    assert upgrade["target"]["def_version"] == item["workflow_version"] + 1
    assert upgrade["current"]["config_version"] == 1

    r = await client.post(
        f"{API}/work-items/{item['display_id']}/upgrade-workflow",
        json={"row_version": item["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["changed"] is True
    upgraded = body["data"]
    assert upgraded["workflow_config_key"] == "up_flow"
    assert upgraded["workflow_config_version"] == 2
    assert upgraded["workflow_config_version_id"] == new_version["id"]
    assert upgraded["workflow_version"] == item["workflow_version"] + 1

    after = await _detail(client, owner_token, item["display_id"])
    assert after["meta"]["workflow_upgrade"]["available"] is False, {
        "item_def": after["data"]["workflow_def_id"],
        "upgraded_def": upgraded["workflow_def_id"],
        "upgrade": after["meta"]["workflow_upgrade"],
    }
    assert after["meta"]["workflow_upgrade"]["blockers"] == []

    history = await client.get(
        f"{API}/work-items/{item['display_id']}/history",
        headers=auth(owner_token),
    )
    assert history.status_code == 200, history.text
    entries = history.json()["data"]
    upgrade_entries = [e for e in entries if e["action"] == "workflow_upgraded"]
    assert len(upgrade_entries) == 1
    entry = upgrade_entries[0]
    assert entry["meta"]["from"]["config_key"] == "up_flow"
    assert entry["meta"]["from"]["config_version"] == 1
    assert entry["meta"]["to"]["config_key"] == "up_flow"
    assert entry["meta"]["to"]["config_version"] == 2
    assert entry["meta"]["from"]["def_version"] == item["workflow_version"]
    assert entry["meta"]["to"]["def_version"] == item["workflow_version"] + 1

    # Idempotent: a second click does not bump row_version or add history.
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/upgrade-workflow",
        json={"row_version": upgraded["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["changed"] is False
    history = await client.get(
        f"{API}/work-items/{item['display_id']}/history",
        headers=auth(owner_token),
    )
    assert len([e for e in history.json()["data"] if e["action"] == "workflow_upgraded"]) == 1


async def test_upgrade_is_blocked_when_status_disappears(server, owner_token: str) -> None:
    client, _settings, _app = server
    config = await _fork(client, owner_token, "default", "shrunk_flow", "Shrunk Flow")
    await _create_project(client, owner_token, "SHRK", config["version"]["id"])
    item = await _create_story(client, owner_token, "SHRK")
    assert item["status"] == "TODO"

    new_version = await _save(
        client,
        owner_token,
        "shrunk_flow",
        content_text=_config_text(key="shrunk_flow", name="Shrunk Flow", shrink_story=True),
        base_version_id=config["version"]["id"],
    )
    await _switch_project(client, owner_token, "SHRK", new_version["id"])

    detail = await _detail(client, owner_token, item["display_id"])
    upgrade = detail["meta"]["workflow_upgrade"]
    assert upgrade["available"] is False
    assert "STATUS_NOT_IN_TARGET" in {b["code"] for b in upgrade["blockers"]}

    r = await client.post(
        f"{API}/work-items/{item['display_id']}/upgrade-workflow",
        json={"row_version": item["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["code"] == "WORKFLOW_UPGRADE_BLOCKED"
    assert "STATUS_NOT_IN_TARGET" in {blocker["code"] for blocker in error["details"]["blockers"]}

    # Nothing was written: the item still points at the old definition.
    after = await _detail(client, owner_token, item["display_id"])
    assert after["data"]["workflow_def_id"] == item["workflow_def_id"]
    assert after["data"]["row_version"] == item["row_version"]
    assert after["data"]["workflow_config_version"] == 1
