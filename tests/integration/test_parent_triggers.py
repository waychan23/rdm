"""Integration: child status changes cascade to parent statuses (RDM-79)."""

from __future__ import annotations

import pyjson5

import rdm.application.services.step_service as step_service_module
import rdm.application.services.workflow_version_service as workflow_version_module
import rdm.application.services.workitem_service as workitem_service_module
import rdm.interfaces.http.workitem as http_workitem_module
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec
from tests.workflow_support import load_test_spec_text

API = "/api/v1"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _trigger_spec() -> WorkflowSpec:
    """Test contract + the three rules from the RDM-79 example."""
    raw = pyjson5.loads(load_test_spec_text())
    raw["version"] = 4
    # The example rule targets TO_REVIEW -> DONE; the contract has two steps to
    # DONE there, and an automatic transition cannot pick one. Keep a single
    # approval step so the rule is applicable.
    raw["workflow_defs"]["task_standard"]["steps"]["TO_REVIEW"] = [
        step
        for step in raw["workflow_defs"]["task_standard"]["steps"]["TO_REVIEW"]
        if step["key"] != "CODE_REVIEW_TASKS"
    ]
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = [
        {
            "when": {
                "from": ["TODO"],
                "to": ["IN_PROGRESS"],
                "task_types": ["frontend", "backend", "fullstack"],
            },
            "parent": {"from": ["TODO"], "to": "IN_PROGRESS"},
        },
        {
            "when": {"to": ["DONE"]},
            "parent": {"from": ["TO_REVIEW"], "to": "DONE"},
        },
        {
            "when": {"to": ["DONE"]},
            "all_children_terminal": True,
            "parent": {"from": ["TO_TEST"], "to": "DONE"},
        },
    ]
    return WorkflowSpec.model_validate(raw)


async def _project(client, token: str) -> None:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=_auth(token)
    )
    assert r.status_code == 201, r.text


async def _create(
    client,
    token: str,
    *,
    kind: str,
    title: str,
    parent: dict | None = None,
    task_type: str | None = None,
) -> dict:
    body: dict = {"kind": kind, "title": title, "assignee": "me"}
    if parent is not None:
        body["parent"] = parent["display_id"]
    if task_type is not None:
        body["task_type"] = task_type
    r = await client.post(f"{API}/projects/DEMO/work-items", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _detail(client, token: str, ref: str) -> dict:
    r = await client.get(f"{API}/work-items/{ref}", headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def _status(client, token: str, ref: str) -> str:
    return (await _detail(client, token, ref))["data"]["status"]


async def _set_review_content(client, token: str, ref: str, value: str) -> None:
    detail = await _detail(client, token, ref)
    r = await client.patch(
        f"{API}/work-items/{ref}",
        json={"row_version": detail["data"]["row_version"], "review_content_md": value},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text


async def _move(client, token: str, ref: str, to: str, *, reason: str | None = None) -> dict:
    detail = await _detail(client, token, ref)
    r = await client.post(
        f"{API}/work-items/{ref}/transition",
        json={"to": to, "row_version": detail["data"]["row_version"], "reason": reason},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_child_change_cascades_through_two_parents(server, owner_token: str, monkeypatch):
    client, _settings, _app = server
    engine = WorkflowEngine(_trigger_spec())
    for module in (
        step_service_module,
        workitem_service_module,
        workflow_version_module,
        http_workitem_module,
    ):
        monkeypatch.setattr(module, "load_engine", lambda: engine)

    await _project(client, owner_token)
    story = await _create(client, owner_token, kind="story", title="W1")
    dev = await _create(
        client, owner_token, kind="task", title="W2", parent=story, task_type="fullstack"
    )
    testing = await _create(
        client, owner_token, kind="task", title="W3", parent=story, task_type="testing"
    )
    review = await _create(
        client, owner_token, kind="task", title="W4", parent=dev, task_type="code_review"
    )

    # Rule 1: a dev child starting work starts the story.
    await _move(client, owner_token, dev["display_id"], "IN_PROGRESS")
    assert await _status(client, owner_token, story["display_id"]) == "IN_PROGRESS"

    # Finish the sibling so the story's children are all terminal later.
    await _move(client, owner_token, testing["display_id"], "CANCELLED")
    await _move(client, owner_token, story["display_id"], "TO_TEST")
    await _move(client, owner_token, dev["display_id"], "TO_REVIEW")
    # The review step's required_fields gate still applies to automatic
    # transitions; satisfy it so rule 2 can fire.
    await _set_review_content(client, owner_token, dev["display_id"], "LGTM")

    # Rule 2 + rule 3: W4 done -> W2 done -> story done, in one cascade.
    await _move(client, owner_token, review["display_id"], "IN_PROGRESS")
    await _move(client, owner_token, review["display_id"], "IN_REVIEW")
    await _move(client, owner_token, review["display_id"], "DONE", reason="approved")

    assert await _status(client, owner_token, dev["display_id"]) == "DONE"
    assert await _status(client, owner_token, story["display_id"]) == "DONE"


async def test_trigger_is_skipped_when_parent_state_does_not_match(
    server, owner_token: str, monkeypatch
):
    client, _settings, _app = server
    engine = WorkflowEngine(_trigger_spec())
    for module in (
        step_service_module,
        workitem_service_module,
        workflow_version_module,
        http_workitem_module,
    ):
        monkeypatch.setattr(module, "load_engine", lambda: engine)

    await _project(client, owner_token)
    story = await _create(client, owner_token, kind="story", title="S2")
    child = await _create(
        client, owner_token, kind="task", title="T2", parent=story, task_type="fullstack"
    )
    # The story has already left TODO, so rule 1 (TODO -> IN_PROGRESS) must not
    # fire again.
    await _move(client, owner_token, story["display_id"], "IN_PROGRESS")
    await _move(client, owner_token, child["display_id"], "IN_PROGRESS")

    assert await _status(client, owner_token, story["display_id"]) == "IN_PROGRESS"
    # Rule 2 requires the parent to be in TO_REVIEW; it is not, so nothing runs.
    await _move(client, owner_token, child["display_id"], "TO_REVIEW")
    assert await _status(client, owner_token, story["display_id"]) == "IN_PROGRESS"


def _child_trigger_spec(kinds: list[str]) -> WorkflowSpec:
    raw = pyjson5.loads(load_test_spec_text())
    raw["version"] = 4
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"kinds": kinds},
            "all_children_terminal": True,
            "self": {"from": ["TO_TEST"], "to": "DONE"},
        }
    ]
    return WorkflowSpec.model_validate(raw)


def _install_engine(monkeypatch, engine: WorkflowEngine) -> None:
    for module in (
        step_service_module,
        workitem_service_module,
        workflow_version_module,
        http_workitem_module,
    ):
        monkeypatch.setattr(module, "load_engine", lambda: engine)


async def _story_with_task_and_issue(client, token: str, title: str) -> tuple[dict, dict, dict]:
    story = await _create(client, token, kind="story", title=title)
    task = await _create(client, token, kind="task", title=f"{title}-task", parent=story)
    issue = await _create(client, token, kind="issue", title=f"{title}-issue", parent=story)
    await _move(client, token, story["display_id"], "IN_PROGRESS")
    await _move(client, token, story["display_id"], "TO_TEST")
    return story, task, issue


async def test_all_children_terminal_accepts_mixed_kinds(server, owner_token: str, monkeypatch):
    """A parent-side rule matches task and issue children without duplication."""
    client, _settings, _app = server
    _install_engine(monkeypatch, WorkflowEngine(_child_trigger_spec(["task", "issue"])))

    await _project(client, owner_token)
    story, task, issue = await _story_with_task_and_issue(client, owner_token, "MIX")

    await _move(client, owner_token, task["display_id"], "CANCELLED")
    # The issue child is still open, so the aggregate condition is false.
    assert await _status(client, owner_token, story["display_id"]) == "TO_TEST"

    await _move(client, owner_token, issue["display_id"], "CANCELLED")
    assert await _status(client, owner_token, story["display_id"]) == "DONE"


async def test_child_trigger_kind_filter_skips_other_kinds(server, owner_token: str, monkeypatch):
    client, _settings, _app = server
    _install_engine(monkeypatch, WorkflowEngine(_child_trigger_spec(["task"])))

    await _project(client, owner_token)
    story, task, issue = await _story_with_task_and_issue(client, owner_token, "KIND")

    # The last child to become terminal is an issue, which this rule ignores.
    await _move(client, owner_token, task["display_id"], "CANCELLED")
    await _move(client, owner_token, issue["display_id"], "CANCELLED")

    assert await _status(client, owner_token, story["display_id"]) == "TO_TEST"


def _child_rule_spec(rule: dict) -> WorkflowSpec:
    raw = pyjson5.loads(load_test_spec_text())
    raw["version"] = 4
    raw["kinds"]["story"]["child_triggers"] = [rule]
    return WorkflowSpec.model_validate(raw)


async def _story_with_child(client, token: str, title: str, child_kind: str) -> tuple[dict, dict]:
    story = await _create(client, token, kind="story", title=title)
    child = await _create(
        client, token, kind=child_kind, title=f"{title}-{child_kind}", parent=story
    )
    await _move(client, token, story["display_id"], "IN_PROGRESS")
    await _move(client, token, story["display_id"], "TO_TEST")
    return story, child


async def test_when_any_matches_either_child_kind(server, owner_token: str, monkeypatch):
    client, _settings, _app = server
    engine = WorkflowEngine(
        _child_rule_spec(
            {
                "when": {
                    "any": [
                        {"kinds": ["task"], "to": ["CANCELLED"]},
                        {"kinds": ["issue"], "to": ["CANCELLED"]},
                    ]
                },
                "self": {"from": ["TO_TEST"], "to": "DONE"},
            }
        )
    )
    _install_engine(monkeypatch, engine)
    await _project(client, owner_token)

    task_story, task = await _story_with_child(client, owner_token, "ANY-TASK", "task")
    issue_story, issue = await _story_with_child(client, owner_token, "ANY-ISSUE", "issue")

    await _move(client, owner_token, task["display_id"], "CANCELLED")
    assert await _status(client, owner_token, task_story["display_id"]) == "DONE"
    # The issue story is untouched until its own child matches a branch.
    assert await _status(client, owner_token, issue_story["display_id"]) == "TO_TEST"

    await _move(client, owner_token, issue["display_id"], "CANCELLED")
    assert await _status(client, owner_token, issue_story["display_id"]) == "DONE"


async def test_any_children_terminal_fires_on_first_terminal_child(
    server, owner_token: str, monkeypatch
):
    client, _settings, _app = server
    engine = WorkflowEngine(
        _child_rule_spec(
            {
                "when": {"kinds": ["task", "issue"]},
                "any_children_terminal": True,
                "self": {"from": ["TO_TEST"], "to": "IN_PROGRESS"},
            }
        )
    )
    _install_engine(monkeypatch, engine)
    await _project(client, owner_token)

    story, task, _issue = await _story_with_task_and_issue(client, owner_token, "ANYCHILD")
    await _move(client, owner_token, task["display_id"], "CANCELLED")
    assert await _status(client, owner_token, story["display_id"]) == "IN_PROGRESS"


async def test_min_children_terminal_waits_for_the_threshold(server, owner_token: str, monkeypatch):
    client, _settings, _app = server
    engine = WorkflowEngine(
        _child_rule_spec(
            {
                "when": {"kinds": ["task", "issue"]},
                "min_children_terminal": 2,
                "self": {"from": ["TO_TEST"], "to": "DONE"},
            }
        )
    )
    _install_engine(monkeypatch, engine)
    await _project(client, owner_token)

    story, task, issue = await _story_with_task_and_issue(client, owner_token, "MIN")
    await _move(client, owner_token, task["display_id"], "CANCELLED")
    assert await _status(client, owner_token, story["display_id"]) == "TO_TEST"

    await _move(client, owner_token, issue["display_id"], "CANCELLED")
    assert await _status(client, owner_token, story["display_id"]) == "DONE"
