"""Accept-Language negotiation for REST errors, workflow data and notifications."""

from __future__ import annotations

import httpx

from tests.support import make_member

API = "/api/v1"


def auth(token: str, locale: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if locale is not None:
        headers["Accept-Language"] = locale
    return headers


async def _project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def test_workflow_dto_is_localized(server, owner_token: str) -> None:
    client, _settings, _app = server
    zh = (await client.get(f"{API}/workflow", headers=auth(owner_token, "zh-CN"))).json()["data"]
    en = (await client.get(f"{API}/workflow", headers=auth(owner_token, "en"))).json()["data"]

    assert zh["kinds"]["issue"]["label"] == "缺陷"
    assert en["kinds"]["issue"]["label"] == "Bug"
    assert zh["kinds"]["task"]["steps"]["TODO"][0]["name"] == "开始"
    assert en["kinds"]["task"]["steps"]["TODO"][0]["name"] == "Start"
    zh_types = {row["value"]: row["label"] for row in zh["task_types"]}
    en_types = {row["value"]: row["label"] for row in en["task_types"]}
    assert zh_types["other"] == "其他"
    assert en_types["other"] == "Other"


async def test_error_envelope_is_localized(server, owner_token: str) -> None:
    client, _settings, _app = server
    zh = await client.get(f"{API}/workflow?kind=nope", headers=auth(owner_token, "zh-CN"))
    en = await client.get(f"{API}/workflow?kind=nope", headers=auth(owner_token, "en"))
    assert zh.status_code == en.status_code == 422
    assert "未知 kind" in zh.json()["error"]["message"]
    assert "Unknown kind" in en.json()["error"]["message"]


async def test_notification_title_is_localized_for_recipient(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    alice_id, alice_token = await make_member(client, owner_token, "DEMO", "alice", ["worker"])
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "i18n notification"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    display_id = r.json()["data"]["display_id"]
    r = await client.post(
        f"{API}/work-items/{display_id}/assign",
        json={"member": alice_id},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text

    zh = (await client.get(f"{API}/notifications", headers=auth(alice_token, "zh-CN"))).json()
    en = (await client.get(f"{API}/notifications", headers=auth(alice_token, "en"))).json()
    assert zh["data"][0]["title"] == f"你被指派了 {display_id}"
    assert en["data"][0]["title"] == f"You were assigned {display_id}"
    # The wire shape stays stable: no title_key/title_params leak to clients.
    assert "title_key" not in en["data"][0]
    assert "title_params" not in en["data"][0]
