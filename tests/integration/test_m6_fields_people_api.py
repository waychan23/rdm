"""Integration: M6 participants, reviewer, review content, custom fields, perms."""

from __future__ import annotations

from tests.support import make_member

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client, token: str, key: str = "DEMO") -> None:
    r = await client.post(f"{API}/projects", json={"key": key, "name": key}, headers=auth(token))
    assert r.status_code == 201, r.text


async def _item(client, token: str, payload: dict, key: str = "DEMO") -> dict:
    r = await client.post(f"{API}/projects/{key}/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _detail(client, token: str, ref: str) -> dict:
    r = await client.get(f"{API}/work-items/{ref}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def test_create_assignee_and_creator_participant(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    dev_id, _dev = await make_member(client, owner_token, "DEMO", "dev", ["worker"])

    own = await _item(client, owner_token, {"kind": "task", "title": "mine", "assignee": "me"})
    assert own["assignee"]["name"] == "owner"
    assert own["participants"] == []
    assert own["task_type"] == "other"

    handed = await _item(
        client, owner_token, {"kind": "task", "title": "handed", "assignee": "dev"}
    )
    assert handed["assignee"]["id"] == dev_id
    assert [p["name"] for p in handed["participants"]] == ["owner"]

    detail = await _detail(client, owner_token, handed["display_id"])
    assert [p["name"] for p in detail["data"]["participants"]] == ["owner"]

    # Unassigned items keep the creator as a participant (never edit-locked).
    free = await _item(client, owner_token, {"kind": "task", "title": "free"})
    assert [p["name"] for p in free["participants"]] == ["owner"]


async def test_participants_reviewer_custom_fields_roundtrip(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    dev_id, _dev = await make_member(client, owner_token, "DEMO", "dev", ["worker"])

    item = await _item(
        client,
        owner_token,
        {
            "kind": "task",
            "title": "review",
            "task_type": "code_review",
            "assignee": "me",
            "participants": ["dev"],
            "reviewer": ["dev"],
            "review_content_md": "API review done",
            "custom_fields": {
                "review_scope": "frontend + api",
                "risk_score": 3,
                "observers": ["dev"],
            },
        },
    )
    assert [p["id"] for p in item["participants"]] == [dev_id]
    assert [p["id"] for p in item["reviewer"]] == [dev_id]
    assert item["review_content_md"] == "API review done"
    assert item["custom_fields"] == {
        "review_scope": "frontend + api",
        "risk_score": 3,
        "observers": [dev_id],
    }

    r = await client.get(f"{API}/projects/DEMO/work-items?reviewer=dev", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    assert [i["display_id"] for i in r.json()["data"]] == [item["display_id"]]

    r = await client.get(f"{API}/projects/DEMO/work-items?q=API", headers=auth(owner_token))
    assert [i["display_id"] for i in r.json()["data"]] == [item["display_id"]]

    # Full replacement: [] / {} clears the fields.
    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={
            "row_version": item["row_version"],
            "participants": [],
            "reviewer": [],
            "custom_fields": {},
            "review_content_md": None,
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    cleared = r.json()["data"]
    assert cleared["participants"] == []
    assert cleared["reviewer"] == []
    assert cleared["custom_fields"] == {}
    assert cleared["review_content_md"] is None

    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={"row_version": cleared["row_version"], "custom_fields": {"nope": 1}},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_edit_and_assign_permissions(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)
    dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])
    other_id, other_token = await make_member(client, owner_token, "DEMO", "other", ["worker"])
    _mgr_id, mgr_token = await make_member(client, owner_token, "DEMO", "mgr", ["manager"])

    task = await _item(client, owner_token, {"kind": "task", "title": "t", "assignee": "dev"})

    # A non-editor worker cannot edit, and cannot take over an assigned item.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "title": "hijack"},
        headers=auth(other_token),
    )
    assert r.status_code == 403
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/assign",
        json={"member": "me"},
        headers=auth(other_token),
    )
    assert r.status_code == 403

    # Assignee and manager can edit.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "title": "dev edit"},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": version, "title": "mgr edit"},
        headers=auth(mgr_token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]

    # Making `other` a participant grants edit rights.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": version, "participants": ["other"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": version, "title": "participant edit"},
        headers=auth(other_token),
    )
    assert r.status_code == 200, r.text

    # Self-claim an unassigned item, then edit it.
    unassigned = await _item(client, owner_token, {"kind": "task", "title": "free"})
    r = await client.post(
        f"{API}/work-items/{unassigned['display_id']}/assign",
        json={"member": "me"},
        headers=auth(other_token),
    )
    assert r.status_code == 200, r.text
    claimed = r.json()["data"]
    assert claimed["assignee"]["id"] == other_id
    r = await client.patch(
        f"{API}/work-items/{unassigned['display_id']}",
        json={"row_version": claimed["row_version"], "title": "claimed edit"},
        headers=auth(other_token),
    )
    assert r.status_code == 200, r.text


async def test_task_type_aliases_and_subtype_workflow(server, owner_token: str) -> None:
    client, _s, _app = server
    await _project(client, owner_token)

    qa = await _item(client, owner_token, {"kind": "task", "title": "qa", "task_type": "qa"})
    assert qa["task_type"] == "testing"
    assert qa["fields"]["task_type"] == "testing"

    ux = await _item(client, owner_token, {"kind": "task", "title": "ux", "task_type": "ux_design"})
    assert ux["task_type"] == "ui_design"

    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "bad", "task_type": "nope"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422

    r = await client.patch(
        f"{API}/work-items/{qa['display_id']}",
        json={"row_version": qa["row_version"], "task_type": "backend"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert "不可修改" in r.json()["error"]["message"]

    review = await _item(
        client,
        owner_token,
        {"kind": "task", "title": "review", "task_type": "code_review", "assignee": "me"},
    )
    assert review["status"] == "TODO"
    listed = (
        await client.get(
            f"{API}/projects/DEMO/work-items",
            params={"kind": "task", "limit": 100},
            headers=auth(owner_token),
        )
    ).json()["data"]
    by_id = {row["display_id"]: row for row in listed}
    assert by_id[qa["display_id"]]["task_type"] == "testing"
    assert by_id[review["display_id"]]["task_type"] == "code_review"
    detail = await _detail(client, owner_token, review["display_id"])
    assert detail["meta"]["allowed_transitions"] == ["IN_PROGRESS", "CANCELLED"]

    r = await client.post(
        f"{API}/work-items/{review['display_id']}/transition",
        json={"to": "IN_PROGRESS", "row_version": review["row_version"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["allowed_transitions"] == ["IN_REVIEW", "CANCELLED"]

    # Tasks can now contain tasks.
    child = await _item(
        client,
        owner_token,
        {"kind": "task", "title": "sub", "parent": review["display_id"]},
    )
    assert child["parent_id"] == review["id"]
    detail = await _detail(client, owner_token, review["display_id"])
    assert detail["meta"]["allowed_child_kinds"] == ["task"]


async def test_workflow_dto_exposes_task_types_and_subtypes(server, owner_token: str) -> None:
    client, _s, _app = server
    r = await client.get(f"{API}/workflow", headers=auth(owner_token))
    assert r.status_code == 200
    dto = r.json()["data"]
    assert {t["value"] for t in dto["task_types"]} >= {
        "code_review",
        "testing",
        "ui_design",
        "test_case_design",
    }
    task = dto["kinds"]["task"]
    assert task["fields"]["reviewer"] is True
    assert task["fields"]["review_content"] is True
    assert "code_review" in task["subtypes"]
    assert task["subtypes"]["code_review"]["states"] == [
        "TODO",
        "IN_PROGRESS",
        "IN_REVIEW",
        "DONE",
        "CANCELLED",
    ]
    assert task["subtypes"]["code_review"]["fields"]["custom"]
