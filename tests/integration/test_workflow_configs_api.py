"""Workflow config import, editing and project selection (RDM-84)."""

from __future__ import annotations

import json

import httpx
import pyjson5
import pytest

from rdm.domain.workflow.loader import load_spec_text
from rdm.infrastructure.db.workflow_config_sync import sync_workflow_configs

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _custom_config_text(
    *,
    key: str,
    name: str,
    initial: str = "TODO",
    label: str | None = None,
) -> str:
    raw = pyjson5.loads(load_spec_text())
    raw["key"] = key
    raw["name"] = name
    raw["kinds"]["story"]["initial"] = initial
    if label is not None:
        raw["kinds"]["story"]["label"] = label
    return json.dumps(raw, ensure_ascii=False)


async def _default_config(client: httpx.AsyncClient, token: str) -> dict:
    r = await client.get(f"{API}/workflow-configs", headers=auth(token))
    assert r.status_code == 200, r.text
    configs = r.json()["data"]
    default = next((c for c in configs if c["key"] == "default"), None)
    assert default is not None, configs
    return default


async def _detail(client: httpx.AsyncClient, token: str, key: str) -> dict:
    r = await client.get(f"{API}/workflow-configs/{key}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


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
) -> httpx.Response:
    return await client.post(
        f"{API}/workflow-configs/{key}/versions",
        json={"content_text": content_text, "base_version_id": base_version_id},
        headers=auth(token),
    )


async def test_startup_imports_builtin_config_and_is_idempotent(server, owner_token: str) -> None:
    client, settings, _app = server
    default = await _default_config(client, owner_token)
    assert default["is_builtin"] is True
    assert default["enabled"] is True
    assert default["active_version"]["version"] == 1
    assert default["active_version"]["schema_version"] == 4
    assert default["version_count"] == 1

    detail = await _detail(client, owner_token, "default")
    assert detail["active_version"]["content_text"]
    assert detail["versions"][0]["source_version_id"] is None

    # A second startup import of the same (version, revision, content) is a
    # no-op: no duplicate versions appear.
    report = sync_workflow_configs(settings)
    assert report.imported == []
    assert any(item.startswith("default v1") for item in report.unchanged)
    again = await _detail(client, owner_token, "default")
    assert len(again["versions"]) == 1


async def test_builtin_is_readonly_but_can_be_forked_and_edited(server, owner_token: str) -> None:
    client, _settings, _app = server
    default = await _default_config(client, owner_token)
    active = default["active_version"]

    r = await _save(
        client,
        owner_token,
        "default",
        content_text=_custom_config_text(key="default", name="默认工作流"),
        base_version_id=active["id"],
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    custom = await _fork(client, owner_token, "default", "custom", "自定义工作流")
    assert custom["version"]["source_version_id"] == active["id"]
    assert custom["config"]["is_builtin"] is False
    assert custom["config"]["active_version"]["version"] == 1

    content = _custom_config_text(key="custom", name="自定义工作流", label="自定义需求")
    r = await _save(
        client,
        owner_token,
        "custom",
        content_text=content,
        base_version_id=custom["version"]["id"],
    )
    assert r.status_code == 201, r.text
    saved = r.json()["data"]["version"]
    assert saved["version"] == 2
    assert saved["source_version_id"] == custom["version"]["id"]

    # Editing must build on the current active version, not a middle one.
    r = await _save(
        client,
        owner_token,
        "custom",
        content_text=content,
        base_version_id=custom["version"]["id"],
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CONFLICT_VERSION"

    detail = await _detail(client, owner_token, "custom")
    assert [v["version"] for v in detail["versions"]] == [2, 1]
    assert detail["versions"][0]["is_active"] is True
    assert detail["versions"][1]["is_active"] is False

    # Forking a middle version is rejected by the service (source is always
    # resolved from the key's current active version, so this means the key
    # must exist and be active).


async def test_disabled_config_cannot_be_selected_by_new_projects(server, owner_token: str) -> None:
    client, _settings, _app = server
    custom = await _fork(client, owner_token, "default", "disabled_flow", "停用流")
    version_id = custom["version"]["id"]

    r = await client.patch(
        f"{API}/workflow-configs/disabled_flow",
        json={"enabled": False},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["enabled"] is False

    r = await client.post(
        f"{API}/projects",
        json={
            "key": "DSBL",
            "name": "Disabled",
            "workflow_config_version_id": version_id,
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    # Re-enabling makes it selectable again.
    r = await client.patch(
        f"{API}/workflow-configs/disabled_flow",
        json={"enabled": True},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{API}/projects",
        json={
            "key": "ENBL",
            "name": "Enabled",
            "workflow_config_version_id": version_id,
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["workflow_config_version_id"] == version_id


async def test_project_runs_on_its_selected_workflow(server, owner_token: str) -> None:
    client, _settings, _app = server
    custom = await _fork(client, owner_token, "default", "story_flow", "Story Flow")
    content = _custom_config_text(
        key="story_flow",
        name="Story Flow",
        initial="IN_PROGRESS",
        label="Custom story",
    )
    r = await _save(
        client,
        owner_token,
        "story_flow",
        content_text=content,
        base_version_id=custom["version"]["id"],
    )
    assert r.status_code == 201, r.text
    version_id = r.json()["data"]["version"]["id"]

    r = await client.post(
        f"{API}/projects",
        json={
            "key": "FLOW",
            "name": "Flow",
            "workflow_config_version_id": version_id,
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        f"{API}/projects/FLOW/work-items",
        json={"kind": "story", "title": "uses custom workflow"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["status"] == "IN_PROGRESS"

    # A project without an explicit selection keeps the packaged default.
    r = await client.post(
        f"{API}/projects",
        json={"key": "PLAIN", "name": "Plain"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["workflow_config_version_id"] is None
    r = await client.post(
        f"{API}/projects/PLAIN/work-items",
        json={"kind": "story", "title": "uses default workflow"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["status"] == "TODO"

    # /workflow?project= reflects the selected config.
    r = await client.get(
        f"{API}/workflow", params={"project": "FLOW", "kind": "story"}, headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["kinds"]["story"]["label"] == "Custom story"


async def test_project_can_switch_to_a_newer_config_version(server, owner_token: str) -> None:
    client, _settings, _app = server
    custom = await _fork(client, owner_token, "default", "switch_flow", "Switch Flow")
    r = await client.post(
        f"{API}/projects",
        json={
            "key": "SWCH",
            "name": "Switch",
            "workflow_config_version_id": custom["version"]["id"],
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    content = _custom_config_text(key="switch_flow", name="Switch Flow", initial="IN_PROGRESS")
    r = await _save(
        client,
        owner_token,
        "switch_flow",
        content_text=content,
        base_version_id=custom["version"]["id"],
    )
    assert r.status_code == 201, r.text
    new_version = r.json()["data"]["version"]

    r = await client.patch(
        f"{API}/projects/SWCH",
        json={"workflow_config_version_id": new_version["id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["workflow_config_version_id"] == new_version["id"]

    # Existing items keep their pinned definition; new items use the new flow.
    r = await client.post(
        f"{API}/projects/SWCH/work-items",
        json={"kind": "story", "title": "after switch"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["status"] == "IN_PROGRESS"


async def test_new_json5_file_is_imported_and_stale_revisions_are_refused(
    server, owner_token: str
) -> None:
    client, settings, _app = server
    directory = settings.workflow_configs_dir
    path = directory / "extra-flow.json5"

    raw = pyjson5.loads(load_spec_text())
    raw["key"] = "extra"
    raw["name"] = "Extra"
    raw["kinds"]["story"]["label"] = "Extra story"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    report = sync_workflow_configs(settings)
    assert any(item.startswith("extra v1") for item in report.imported)
    detail = await _detail(client, owner_token, "extra")
    assert detail["is_builtin"] is True
    assert detail["active_version"]["revision"] == raw["revision"]

    # Changing content without bumping revision is a startup error: the
    # operator must make the new version explicit.
    raw["kinds"]["story"]["label"] = "Changed without revision"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="revision"):
        sync_workflow_configs(settings)

    # A stale schema version is never imported.
    raw["revision"] = raw["revision"] + 1
    raw["version"] = 3
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="最新版本"):
        sync_workflow_configs(settings)


async def test_config_edit_rejects_missing_base_kinds(server, owner_token: str) -> None:
    client, _settings, _app = server
    custom = await _fork(client, owner_token, "default", "partial", "Partial")

    raw = pyjson5.loads(load_spec_text())
    raw["key"] = "partial"
    raw["name"] = "Partial"

    for kind in ("epic", "story", "issue", "task", "sprint"):
        broken = {**raw, "kinds": {k: v for k, v in raw["kinds"].items() if k != kind}}
        r = await _save(
            client,
            owner_token,
            "partial",
            content_text=json.dumps(broken, ensure_ascii=False),
            base_version_id=custom["version"]["id"],
        )
        assert r.status_code == 422, (kind, r.text)
        assert "基础 kind" in r.json()["error"]["message"]

    broken = {**raw, "task_types": {k: v for k, v in raw["task_types"].items() if k != "other"}}
    r = await _save(
        client,
        owner_token,
        "partial",
        content_text=json.dumps(broken, ensure_ascii=False),
        base_version_id=custom["version"]["id"],
    )
    assert r.status_code == 422, r.text
    assert "other" in r.json()["error"]["message"]


async def test_project_detail_echoes_old_disabled_config(server, owner_token: str) -> None:
    client, _settings, _app = server
    custom = await _fork(client, owner_token, "default", "echo_flow", "Echo Flow")
    v1 = custom["version"]["id"]

    r = await client.post(
        f"{API}/projects",
        json={"key": "ECHO", "name": "Echo", "workflow_config_version_id": v1},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    # v2 becomes active; v1 is no longer in any list endpoint.
    r = await _save(
        client,
        owner_token,
        "echo_flow",
        content_text=_custom_config_text(key="echo_flow", name="Echo Flow", label="Echo 2"),
        base_version_id=v1,
    )
    assert r.status_code == 201, r.text
    v2 = r.json()["data"]["version"]["id"]
    assert v2 != v1

    r = await client.patch(
        f"{API}/workflow-configs/echo_flow",
        json={"enabled": False},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text

    config_detail = await _detail(client, owner_token, "echo_flow")
    r = await client.get(f"{API}/projects/ECHO", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    echoed = r.json()["data"]["workflow_config"]
    assert echoed == {
        "config_id": config_detail["id"],
        "key": "echo_flow",
        "name": "Echo Flow",
        "is_builtin": False,
        "enabled": False,
        "version_id": v1,
        "version": 1,
        "schema_version": 4,
        "revision": pyjson5.loads(load_spec_text())["revision"],
        "is_active": False,
    }

    # Renaming the project must not try to re-select the disabled pinned
    # version; the frontend omits it, and a name-only PATCH succeeds.
    r = await client.patch(
        f"{API}/projects/ECHO",
        json={"name": "Echo renamed"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["workflow_config_version_id"] == v1
