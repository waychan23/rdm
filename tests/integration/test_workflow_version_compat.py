"""Integration: old items keep their pinned workflow definition (§17.120)."""

from __future__ import annotations

import pyjson5

import rdm.application.services.step_service as step_service_module
import rdm.application.services.workitem_service as workitem_service_module
import rdm.interfaces.http.workitem as http_workitem_module
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec
from tests.support import make_member
from tests.workflow_support import load_test_spec_text

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _renamed_spec() -> WorkflowSpec:
    raw = pyjson5.loads(load_test_spec_text())
    steps = raw["workflow_defs"]["task_standard"]["steps"]
    steps["IN_PROGRESS"] = [
        {**step, "key": "SUBMIT_QA"} if step["key"] == "SUBMIT_REVIEW" else step
        for step in steps["IN_PROGRESS"]
        if step["key"] != "BLOCK"
    ]
    return WorkflowSpec.model_validate(raw)


async def _project(client, token: str) -> None:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text


async def _create(client, token: str, assignee: str) -> dict:
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "t", "assignee": assignee},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _move(client, token: str, item: dict, to: str) -> dict:
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/transition",
        json={"to": to, "row_version": item["row_version"]},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _detail(client, token: str, item: dict) -> dict:
    r = await client.get(f"{API}/work-items/{item['display_id']}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def test_old_item_keeps_pinned_definition(server, owner_token: str, monkeypatch) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    dev_id, dev_token = await make_member(client, owner_token, "DEMO", "dev", ["worker"])

    old = await _create(client, owner_token, dev_id)
    old = await _move(client, dev_token, old, "IN_PROGRESS")
    assert old["workflow_version"] == 1
    assert old["status"] == "IN_PROGRESS"

    # Current config now renames the IN_PROGRESS direct step.
    engine = WorkflowEngine(_renamed_spec())
    monkeypatch.setattr(workitem_service_module, "load_engine", lambda: engine)
    monkeypatch.setattr(step_service_module, "load_engine", lambda: engine)
    monkeypatch.setattr(http_workitem_module, "load_engine", lambda: engine)

    new = await _create(client, owner_token, dev_id)
    assert new["workflow_version"] == 2
    new = await _move(client, dev_token, new, "IN_PROGRESS")

    old_detail = await _detail(client, dev_token, old)
    old_keys = {step["key"] for step in old_detail["meta"]["available_steps"]}
    new_detail = await _detail(client, dev_token, new)
    new_keys = {step["key"] for step in new_detail["meta"]["available_steps"]}

    assert "SUBMIT_REVIEW" in old_keys
    assert "SUBMIT_REVIEW" not in new_keys
    assert "SUBMIT_QA" in new_keys

    # The old item can still start the step that no longer exists in the
    # current config, because its pinned definition owns the edge.
    r = await client.post(
        f"{API}/work-items/{old['display_id']}/steps/SUBMIT_REVIEW",
        json={"row_version": old_detail["data"]["row_version"]},
        headers=auth(dev_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "TO_REVIEW"
