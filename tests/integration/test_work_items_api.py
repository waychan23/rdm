"""Integration: WorkItem REST API (plan M1-1): create/update/assign/delete/restore."""

from __future__ import annotations

import httpx

from tests.db import sync_rows

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: httpx.AsyncClient, token: str, key: str = "DEMO") -> None:
    r = await client.post(
        f"{API}/projects",
        json={"key": key, "name": f"项目 {key}"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text


async def _make_member(
    client: httpx.AsyncClient, owner: str, project: str, name: str, roles: list[str]
) -> tuple[str, str]:
    from tests.support import make_member

    return await make_member(client, owner, project, name, roles)


async def test_create_kinds_fields_and_cross_kind_rejection(server, owner_token: str) -> None:
    client, settings, _app = server
    await _create_project(client, owner_token)

    # epic + story with story-only field
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "首个 epic"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    epic = r.json()["data"]
    assert epic["display_id"] == "DEMO-1" and epic["status"] == "TODO"

    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "story",
            "title": "用户故事",
            "parent": "DEMO-1",
            "acceptance_criteria_md": "AC",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    story = r.json()["data"]
    assert story["display_id"] == "DEMO-2"
    assert story["fields"] == {"acceptance_criteria_md": "AC"}
    assert story["parent_id"] == epic["id"]

    # issue with full kind-specific payload
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "issue",
            "title": "白屏",
            "severity": "blocker",
            "environment": "prod",
            "source_story": "DEMO-2",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    issue = r.json()["data"]
    assert issue["fields"]["severity"] == "blocker"
    assert issue["fields"]["source_story_id"] == story["id"]

    # cross-kind field -> VALIDATION_ERROR 422
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "串字段", "severity": "minor"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["field"] == "severity"

    # schema-level bad enum also 422
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "x", "task_type": "nope"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422


async def test_parent_rules(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    epic = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "epic", "title": "e"},
            headers=auth(owner_token),
        )
    ).json()["data"]

    # issue cannot have a parent
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "issue", "title": "i", "parent": epic["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"]["field"] == "parent"

    # task can hang directly under epic
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "t", "parent": "DEMO-1", "task_type": "qa"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["parent_id"] == epic["id"]

    # missing parent reference -> NOT_FOUND
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "s", "parent": "DEMO-99"},
        headers=auth(owner_token),
    )
    assert r.status_code == 404


async def test_update_optimistic_lock_and_assign(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    member_id, _tok = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    created = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": "t", "task_type": "backend"},
            headers=auth(owner_token),
        )
    ).json()["data"]
    ref = created["display_id"]

    # stale row_version -> 409 CONFLICT_VERSION
    r = await client.patch(
        f"{API}/work-items/{ref}",
        json={"row_version": 99, "title": "new"},
        headers=auth(owner_token),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT_VERSION"

    r = await client.patch(
        f"{API}/work-items/{ref}",
        json={"row_version": 0, "title": "新标题", "actual_work_hours": 2.5},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["title"] == "新标题"
    assert body["row_version"] == 1
    assert body["fields"]["actual_work_hours"] == 2.5

    # assign to member
    r = await client.post(
        f"{API}/work-items/{ref}/assign",
        json={"member": "dev"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assignee"] == {
        "id": member_id,
        "name": "dev",
        "display_name": None,
        "type": "human",
    }

    # unknown assignee -> NOT_FOUND
    r = await client.post(
        f"{API}/work-items/{ref}/assign",
        json={"member": "ghost"},
        headers=auth(owner_token),
    )
    assert r.status_code == 404


async def test_detail_carries_allowed_transitions_and_children(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "e"},
        headers=auth(owner_token),
    )
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "s", "parent": "DEMO-1"},
        headers=auth(owner_token),
    )
    r = await client.get(f"{API}/work-items/DEMO-1", headers=auth(owner_token))
    assert r.status_code == 200
    payload = r.json()
    assert payload["meta"]["allowed_transitions"] == ["IN_PROGRESS", "CANCELLED"]
    assert [c["display_id"] for c in payload["meta"]["children"]] == ["DEMO-2"]


async def test_cascade_delete_and_restore_parent_chain(server, owner_token: str) -> None:
    client, settings, _app = server
    await _create_project(client, owner_token)
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "e"},
        headers=auth(owner_token),
    )
    await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "story", "title": "s", "parent": "DEMO-1"},
        headers=auth(owner_token),
    )

    r = await client.delete(f"{API}/work-items/DEMO-1", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] == ["DEMO-1", "DEMO-2"]

    assert (
        await client.get(f"{API}/work-items/DEMO-2", headers=auth(owner_token))
    ).status_code == 404

    # owner can see deleted; restoring the child alone is blocked by parent
    r = await client.get(f"{API}/work-items/DEMO-2?include_deleted=true", headers=auth(owner_token))
    assert r.status_code == 200 and r.json()["data"]["deleted_at"]
    r = await client.post(f"{API}/work-items/DEMO-2/restore", headers=auth(owner_token))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ALREADY_DELETED"

    # restore the root revives the whole batch
    r = await client.post(f"{API}/work-items/DEMO-1/restore", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["restored"] == ["DEMO-1", "DEMO-2"]
    assert (
        await client.get(f"{API}/work-items/DEMO-2", headers=auth(owner_token))
    ).status_code == 200

    # events recorded for created/assigned-less/deleted/restored
    kinds = {
        row[0]
        for row in sync_rows(
            settings,
            "select distinct event_type from event where aggregate_type='work_item'",
        )
    }
    assert {"work_item.created", "work_item.deleted", "work_item.restored"} <= kinds


async def test_list_filters_and_q(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    for kind, title in [("task", "登录 bug"), ("task", "登录优化"), ("epic", "支付")]:
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": kind, "title": title},
            headers=auth(owner_token),
        )
    r = await client.get(
        f"{API}/projects/DEMO/work-items?kind=task&q=登录", headers=auth(owner_token)
    )
    assert r.status_code == 200
    assert {i["display_id"] for i in r.json()["data"]} == {"DEMO-1", "DEMO-2"}

    # Multiple kinds arrive as a comma list from the backlog filter.
    r = await client.get(
        f"{API}/projects/DEMO/work-items?kind=task,epic", headers=auth(owner_token)
    )
    assert r.status_code == 200
    assert {i["display_id"] for i in r.json()["data"]} == {"DEMO-1", "DEMO-2", "DEMO-3"}

    r = await client.get(
        f"{API}/projects/DEMO/work-items?kind=task,story", headers=auth(owner_token)
    )
    assert r.status_code == 200
    assert {i["display_id"] for i in r.json()["data"]} == {"DEMO-1", "DEMO-2"}

    # The search box accepts the display id or its bare number (RDM-88).
    r = await client.get(f"{API}/projects/DEMO/work-items?q=DEMO-2", headers=auth(owner_token))
    assert r.status_code == 200
    assert [i["display_id"] for i in r.json()["data"]] == ["DEMO-2"]

    r = await client.get(f"{API}/projects/DEMO/work-items?q=demo-2", headers=auth(owner_token))
    assert r.status_code == 200
    assert [i["display_id"] for i in r.json()["data"]] == ["DEMO-2"]

    r = await client.get(f"{API}/projects/DEMO/work-items?q=3", headers=auth(owner_token))
    assert r.status_code == 200
    assert [i["display_id"] for i in r.json()["data"]] == ["DEMO-3"]

    # Another project's key is neither a display id nor a text match here.
    r = await client.get(f"{API}/projects/DEMO/work-items?q=OTHER-2", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.json()["data"] == []


async def test_list_q_accepts_display_id_in_sprint_scope(server, owner_token: str) -> None:
    """Sprint-scoped lists filter in memory; the id match must work there too."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    for kind, title in [("task", "登录 bug"), ("task", "支付回调")]:
        r = await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": kind, "title": title},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text

    r = await client.post(
        f"{API}/projects/DEMO/sprints", json={"name": "S1"}, headers=auth(owner_token)
    )
    assert r.status_code == 201, r.text
    sprint_id = r.json()["data"]["id"]
    r = await client.post(
        f"{API}/sprints/{sprint_id}/items",
        json={"items": ["DEMO-1"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.get(
        f"{API}/projects/DEMO/work-items?sprint={sprint_id}&q=DEMO-1",
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert [i["display_id"] for i in r.json()["data"]] == ["DEMO-1"]

    # DEMO-2 is not in the sprint even though the number matches its id.
    r = await client.get(
        f"{API}/projects/DEMO/work-items?sprint={sprint_id}&q=2",
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert r.json()["data"] == []


async def _complete_task(client: httpx.AsyncClient, token: str, item: dict) -> dict:
    """Drive a task through the workflow to DONE."""
    version = item["row_version"]
    for to in ("IN_PROGRESS", "TO_REVIEW"):
        r = await client.post(
            f"{API}/work-items/{item['display_id']}/transition",
            json={"to": to, "row_version": version},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text
        version = r.json()["data"]["row_version"]
    # The DONE gate requires a review comment before the step can start.
    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={"row_version": version, "review_content_md": "自测通过"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    version = r.json()["data"]["row_version"]
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/steps/CODE_REVIEW",
        json={"row_version": version, "executors": ["dev"], "note_md": None},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    step = r.json()["meta"]["active_step"]
    r = await client.post(
        f"{API}/work-item-steps/{step['id']}/execute",
        json={"note_md": "self review"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    done = r.json()["data"]
    assert done["status"] == "DONE"
    return done


async def test_list_completed_filter(server, owner_token: str) -> None:
    """`completed` filters by terminal state, which differs per workflow (RDM-45)."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    _dev_id, dev_token = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    async def create(title: str) -> dict:
        r = await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": title, "assignee": "dev"},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]

    done_item = await create("done task")
    open_item = await create("open task")
    epic = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "epic", "title": "open epic"},
        headers=auth(owner_token),
    )
    assert epic.status_code == 201, epic.text
    await _complete_task(client, dev_token, done_item)

    async def ids(query: str) -> set[str]:
        r = await client.get(f"{API}/projects/DEMO/work-items?{query}", headers=auth(owner_token))
        assert r.status_code == 200, r.text
        return {item["display_id"] for item in r.json()["data"]}

    assert await ids("completed=true") == {done_item["display_id"]}
    assert await ids("completed=false") == {open_item["display_id"], "DEMO-3"}
    # Meta total follows the same filter (pagination is computed from it).
    r = await client.get(
        f"{API}/projects/DEMO/work-items?completed=false", headers=auth(owner_token)
    )
    assert r.json()["meta"]["total"] == 2


async def test_list_order_by_created(server, owner_token: str) -> None:
    """The list page sorts by creation time; the default stays display_no (RDM-46)."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    created: list[str] = []
    for title in ("first", "second", "third"):
        r = await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": title},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        created.append(r.json()["data"]["display_id"])

    async def titles(query: str) -> list[str]:
        r = await client.get(f"{API}/projects/DEMO/work-items?{query}", headers=auth(owner_token))
        assert r.status_code == 200, r.text
        return [item["title"] for item in r.json()["data"]]

    assert await titles("") == ["first", "second", "third"]
    assert await titles("order=created_asc") == ["first", "second", "third"]
    assert await titles("order=created_desc") == ["third", "second", "first"]

    r = await client.get(f"{API}/projects/DEMO/work-items?order=bad", headers=auth(owner_token))
    assert r.status_code == 422


async def test_list_includes_sprint_and_planned_dates(server, owner_token: str) -> None:
    """List summaries carry the sprint and planned dates (RDM-59)."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    story = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={
                "kind": "story",
                "title": "planned",
                "planned_start_date": "2026-02-01",
                "planned_end_date": "2026-02-10",
            },
            headers=auth(owner_token),
        )
    ).json()["data"]

    async def row() -> dict:
        r = await client.get(
            f"{API}/projects/DEMO/work-items?kind=story", headers=auth(owner_token)
        )
        assert r.status_code == 200, r.text
        return r.json()["data"][0]

    first = await row()
    assert first["planned_start_date"] == "2026-02-01"
    assert first["planned_end_date"] == "2026-02-10"
    assert first["sprint"] is None

    r = await client.post(
        f"{API}/projects/DEMO/sprints", json={"name": "S1"}, headers=auth(owner_token)
    )
    sprint = r.json()["data"]
    r = await client.post(
        f"{API}/sprints/{sprint['id']}/items",
        json={"items": [story["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    linked = await row()
    assert linked["sprint"] == {"id": sprint["id"], "name": "S1"}


async def test_list_multi_value_filters_and_root_only(server, owner_token: str) -> None:
    """RDM-63: multi status/assignee/participant, subtype and root-only filters."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    dev_id, dev_token = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    async def create(body: dict) -> dict:
        r = await client.post(
            f"{API}/projects/DEMO/work-items", json=body, headers=auth(owner_token)
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]

    epic = await create({"kind": "epic", "title": "epic"})
    story = await create({"kind": "story", "title": "story", "parent": epic["display_id"]})
    frontend = await create(
        {
            "kind": "task",
            "title": "frontend task",
            "task_type": "frontend",
            "parent": story["display_id"],
            "assignee": "dev",
        }
    )
    backend = await create(
        {
            "kind": "task",
            "title": "backend task",
            "task_type": "backend",
            "participants": ["dev"],
        }
    )

    async def ids(query: str) -> set[str]:
        r = await client.get(f"{API}/projects/DEMO/work-items?{query}", headers=auth(owner_token))
        assert r.status_code == 200, r.text
        return {item["display_id"] for item in r.json()["data"]}

    # Subtype narrows tasks only; the non-task kinds selected alongside remain.
    assert await ids("kind=story,task&subtype=frontend") == {
        story["display_id"],
        frontend["display_id"],
    }
    assert await ids("subtype=frontend") == {
        epic["display_id"],
        story["display_id"],
        frontend["display_id"],
    }
    # Root only drops every item with a parent.
    assert await ids("root_only=true") == {epic["display_id"], backend["display_id"]}
    # Multi assignee and participant filters accept comma lists.
    assert await ids(f"assignee=dev,{dev_id}") == {frontend["display_id"]}
    assert await ids("participant=dev") == {backend["display_id"]}
    # Multi status filter.
    assert await ids("status=TODO,DONE") == {
        epic["display_id"],
        story["display_id"],
        frontend["display_id"],
        backend["display_id"],
    }
    assert await ids("status=DONE") == set()

    # RDM-82: has_children filters on direct, non-deleted children.
    assert await ids("has_children=true") == {epic["display_id"], story["display_id"]}
    assert await ids("has_children=false") == {frontend["display_id"], backend["display_id"]}
    assert await ids("has_children=true&kind=story") == {story["display_id"]}
    r = await client.get(
        f"{API}/projects/DEMO/work-items/filter-options?has_children=false",
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text

    # The sprint list is filtered in memory; has_children must still apply.
    r = await client.post(
        f"{API}/projects/DEMO/sprints", json={"name": "S1"}, headers=auth(owner_token)
    )
    sprint = r.json()["data"]
    r = await client.post(
        f"{API}/sprints/{sprint['id']}/items",
        json={"items": [story["display_id"], frontend["display_id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert await ids(f"sprint={sprint['id']}&has_children=true") == {story["display_id"]}
    assert await ids(f"sprint={sprint['id']}&has_children=false") == {frontend["display_id"]}

    # Completed + status combine.
    await _complete_task(client, dev_token, frontend)
    assert await ids("status=TODO") == {
        epic["display_id"],
        story["display_id"],
        backend["display_id"],
    }
    assert await ids("status=TODO&completed=false") == {
        epic["display_id"],
        story["display_id"],
        backend["display_id"],
    }


async def test_list_composite_order(server, owner_token: str) -> None:
    """RDM-63: priority -> planned end -> planned start -> created desc."""
    client, _settings, _app = server
    await _create_project(client, owner_token)

    async def create(title: str, priority: int, end: str | None = None) -> None:
        body: dict = {"kind": "task", "title": title, "priority": priority}
        if end is not None:
            body["planned_end_date"] = end
        r = await client.post(
            f"{API}/projects/DEMO/work-items", json=body, headers=auth(owner_token)
        )
        assert r.status_code == 201, r.text

    await create("low-priority", 4, "2026-01-01")
    await create("urgent-late", 1, "2026-03-01")
    await create("urgent-early", 1, "2026-01-05")
    await create("urgent-undated", 1)

    r = await client.get(
        f"{API}/projects/DEMO/work-items?order=composite", headers=auth(owner_token)
    )
    assert r.status_code == 200, r.text
    assert [item["title"] for item in r.json()["data"]] == [
        "urgent-early",
        "urgent-late",
        "urgent-undated",
        "low-priority",
    ]


async def test_list_priority_and_exclude_filters(server, owner_token: str) -> None:
    """RDM-39 picker: priority multi-select plus exclude ids/statuses."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    created: list[dict] = []
    for title, priority in (("p1", 1), ("p2", 2), ("p3", 3)):
        r = await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": title, "priority": priority},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        created.append(r.json()["data"])

    async def ids(query: str) -> set[str]:
        r = await client.get(f"{API}/projects/DEMO/work-items?{query}", headers=auth(owner_token))
        assert r.status_code == 200, r.text
        return {item["display_id"] for item in r.json()["data"]}

    assert await ids("priority=1,2") == {created[0]["display_id"], created[1]["display_id"]}
    assert await ids(f"exclude_ids={created[0]['id']}") == {
        created[1]["display_id"],
        created[2]["display_id"],
    }
    assert await ids("exclude_status=TODO") == set()
    r = await client.get(
        f"{API}/projects/DEMO/work-items?exclude_ids={created[0]['id']}",
        headers=auth(owner_token),
    )
    assert r.json()["meta"]["total"] == 2


async def test_filter_options_exclude_own_dimension(server, owner_token: str) -> None:
    """RDM-63: facets come from the unpaginated filtered set, each excluding itself."""
    client, _settings, _app = server
    await _create_project(client, owner_token)
    _dev_id, dev_token = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    async def create(title: str, assignee: str | None, participants: list[str]) -> dict:
        body: dict = {"kind": "task", "title": title, "participants": participants}
        if assignee is not None:
            body["assignee"] = assignee
        r = await client.post(
            f"{API}/projects/DEMO/work-items", json=body, headers=auth(owner_token)
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]

    done = await create("done", "dev", [])
    await create("open", None, ["dev"])
    await _complete_task(client, dev_token, done)

    r = await client.get(
        f"{API}/projects/DEMO/work-items/filter-options?kind=task&status=TODO",
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    options = r.json()["data"]
    # The status facet ignores the active status filter.
    assert set(options["statuses"]) == {"TODO", "DONE"}
    # Assignees/participants only come from the TODO subset (done is excluded).
    assert [user["name"] for user in options["assignees"]] == []
    # The creator is auto-added as a participant (§17.89), so owner stays.
    assert {user["name"] for user in options["participants"]} == {"dev", "owner"}


async def test_permissions_worker_and_cross_project(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token, "DEMO")
    _id, worker_token = await _make_member(client, owner_token, "DEMO", "dev", ["worker"])

    # worker cannot manage projects/members
    r = await client.post(
        f"{API}/projects",
        json={"key": "X2", "name": "x"},
        headers=auth(worker_token),
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

    # worker may create work items in own project (soft matrix)
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "mine", "task_type": "docs"},
        headers=auth(worker_token),
    )
    assert r.status_code == 201, r.text

    # Delete cascades and is limited to the creator, managers and owners.
    worker_view = (await client.get(f"{API}/work-items/DEMO-1", headers=auth(worker_token))).json()
    assert worker_view["meta"]["permissions"]["can_delete"] is True
    owner_view = await client.get(f"{API}/work-items/DEMO-1", headers=auth(owner_token))
    assert owner_view.json()["meta"]["permissions"]["can_delete"] is True

    _carol_id, carol_token = await _make_member(client, owner_token, "DEMO", "carol", ["worker"])
    carol_view = (await client.get(f"{API}/work-items/DEMO-1", headers=auth(carol_token))).json()
    assert carol_view["meta"]["permissions"]["can_delete"] is False
    assert (
        await client.delete(f"{API}/work-items/DEMO-1", headers=auth(carol_token))
    ).status_code == 403

    # The creator can delete their own item (soft delete).
    assert (
        await client.delete(f"{API}/work-items/DEMO-1", headers=auth(worker_token))
    ).status_code == 200

    # cross-project access by a non-owner surfaces as NOT_FOUND
    await _create_project(client, owner_token, "OTHER")
    await client.post(
        f"{API}/projects/OTHER/work-items",
        json={"kind": "task", "title": "secret"},
        headers=auth(owner_token),
    )
    # OTHER's first item is OTHER-1 (separate item_seq per project)
    r = await client.get(f"{API}/work-items/OTHER-1", headers=auth(worker_token))
    assert r.status_code == 404


async def test_ulid_accepted_as_id(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)
    created = (
        await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": "by-ulid"},
            headers=auth(owner_token),
        )
    ).json()["data"]
    r = await client.get(f"{API}/work-items/{created['id']}", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.json()["data"]["display_id"] == "DEMO-1"


async def test_planned_dates_are_optional_and_clearable(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)

    # Dates are optional; when present they are plain calendar dates.
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "task",
            "title": "dated",
            "planned_start_date": "2026-11-01",
            "planned_end_date": "2026-11-15",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    item = r.json()["data"]
    assert item["planned_start_date"] == "2026-11-01"
    assert item["planned_end_date"] == "2026-11-15"

    # Malformed dates are rejected by the shared schema/service.
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "bad-date", "planned_start_date": "2026-13-01"},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text

    # PATCH one date and clear the other; absent fields keep their value.
    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={"row_version": item["row_version"], "planned_end_date": None},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["planned_start_date"] == "2026-11-01"
    assert updated["planned_end_date"] is None

    r = await client.patch(
        f"{API}/work-items/{item['display_id']}",
        json={"row_version": updated["row_version"], "planned_end_date": "2026-11-20"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["planned_end_date"] == "2026-11-20"


async def test_priority_is_mandatory_and_validated(server, owner_token: str) -> None:
    client, _settings, _app = server
    await _create_project(client, owner_token)

    async def create(payload: dict) -> httpx.Response:
        return await client.post(
            f"{API}/projects/DEMO/work-items",
            json={"kind": "task", "title": f"p-{payload.get('priority', 'default')}", **payload},
            headers=auth(owner_token),
        )

    # Omitted -> medium (3). 0/"unset" and out-of-range values are rejected.
    r = await create({})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["priority"] == 3
    for invalid in (0, 5):
        r = await create({"priority": invalid})
        assert r.status_code == 422, r.text

    created = {}
    for priority in (1, 2, 3, 4):
        r = await create({"priority": priority})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["priority"] == priority
        created[priority] = r.json()["data"]

    task = created[4]
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "priority": 1},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["priority"] == 1

    # Priority cannot be cleared or set outside 1..4.
    updated = r.json()["data"]
    for invalid in (0, 5, None):
        r = await client.patch(
            f"{API}/work-items/{task['display_id']}",
            json={"row_version": updated["row_version"], "priority": invalid},
            headers=auth(owner_token),
        )
        assert r.status_code == 422, r.text


async def test_detail_meta_includes_root_first_ancestors(server, owner_token: str) -> None:
    """RDM-61: the drawer breadcrumb uses meta.ancestors (root-first)."""
    client, _settings, _app = server
    await _create_project(client, owner_token)

    async def create(body: dict) -> dict:
        r = await client.post(
            f"{API}/projects/DEMO/work-items", json=body, headers=auth(owner_token)
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]

    epic = await create({"kind": "epic", "title": "epic"})
    story = await create({"kind": "story", "title": "story", "parent": epic["display_id"]})
    task = await create({"kind": "task", "title": "task", "parent": story["display_id"]})

    r = await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    meta = r.json()["meta"]
    assert [a["display_id"] for a in meta["ancestors"]] == [
        epic["display_id"],
        story["display_id"],
    ]
    assert meta["parent"]["display_id"] == story["display_id"]

    # The root item has an empty chain.
    r = await client.get(f"{API}/work-items/{epic['display_id']}", headers=auth(owner_token))
    assert r.json()["meta"]["ancestors"] == []
