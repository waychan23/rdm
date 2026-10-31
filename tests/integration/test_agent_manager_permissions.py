"""Integration: humans operate the work items of agents they manage (§17.101).

A human acting as themselves inherits every assignee/executor operation of its
own agents, while history keeps the *actual* operator as the event actor.
"""

from __future__ import annotations

import httpx
import pyjson5

import rdm.application.services.step_service as step_service_module
import rdm.application.services.workitem_service as workitem_service_module
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_spec_text
from rdm.domain.workflow.schema import WorkflowSpec
from tests.conftest import auth
from tests.support import add_to_project, create_agent, create_human, login_pat

API = "/api/v1"


async def _create_task(
    client: httpx.AsyncClient, token: str, *, title: str, assignee: str | None = None
) -> dict:
    payload = {"kind": "task", "title": title, "task_type": "backend"}
    if assignee is not None:
        payload["assignee"] = assignee
    r = await client.post(f"{API}/projects/DEMO/work-items", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _move(client: httpx.AsyncClient, token: str, item: dict, to: str) -> httpx.Response:
    return await client.post(
        f"{API}/work-items/{item['display_id']}/transition",
        json={"to": to, "row_version": item["row_version"], "reason": "推进"},
        headers=auth(token),
    )


async def test_human_operates_items_assigned_to_managed_agent(server, owner_token) -> None:
    client, _settings, _app = server
    await client.post(
        f"{API}/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "DEMO"}
    )
    human_id = await create_human(client, owner_token, "tl")
    # worker only: no manager/owner role, so assignee inheritance is the only
    # source of edit/step permissions.
    await add_to_project(client, owner_token, "DEMO", human_id, ["worker"])
    human_pat = await login_pat(client, "tl")
    agent_id = await create_agent(client, human_pat, "dev")

    task = await _create_task(client, owner_token, title="t", assignee=agent_id)

    # The human manager may edit the agent-assigned item.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "title": "changed by manager"},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]

    # ...and run the agent's direct transition on its behalf.
    r = await _move(client, human_pat, task, "IN_PROGRESS")
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["permissions"]["can_start_steps"] is True
    task = r.json()["data"]

    # ...including starting an approval step (start is assignee-only).
    r = await _move(client, human_pat, task, "TO_REVIEW")
    assert r.status_code == 200, r.text
    task = r.json()["data"]

    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={
            "row_version": task["row_version"],
            "reviewer": [human_id],
            "review_content_md": "manager reviewed",
        },
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]

    r = await client.post(
        f"{API}/work-items/{task['display_id']}/steps/CODE_REVIEW",
        json={"row_version": task["row_version"], "executors": [human_id]},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    assert active is not None
    assert active["can_cancel"] is True

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/cancel",
        json={"row_version": active["row_version"], "reason": "经理取消"},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text

    # History attributes every one of those operations to the human, not the
    # agent that owns the assignment.
    history = (
        await client.get(
            f"{API}/work-items/{task['display_id']}/history", headers=auth(owner_token)
        )
    ).json()["data"]
    human_actions = [
        entry
        for entry in history
        if entry["action"]
        in {"updated", "status_changed", "step_started", "step_cancelled", "step_completed"}
    ]
    assert human_actions
    assert {entry["actor"]["name"] for entry in human_actions} == {"tl"}


async def test_agent_actions_stay_attributed_to_agent(server, owner_token) -> None:
    client, _settings, _app = server
    await client.post(
        f"{API}/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "DEMO"}
    )
    human_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", human_id, ["worker"])
    human_pat = await login_pat(client, "tl")
    agent_id = await create_agent(client, human_pat, "dev")
    agent_pat = await login_pat(client, "tl", act_as_user_id=agent_id)

    task = await _create_task(client, owner_token, title="agent work", assignee=agent_id)
    r = await _move(client, agent_pat, task, "IN_PROGRESS")
    assert r.status_code == 200, r.text

    history = (
        await client.get(
            f"{API}/work-items/{task['display_id']}/history", headers=auth(owner_token)
        )
    ).json()["data"]
    status_changes = [entry for entry in history if entry["action"] == "status_changed"]
    assert status_changes
    assert status_changes[0]["actor"]["name"] == "dev"
    assert status_changes[0]["actor"]["type"] == "agent"


async def test_sibling_agent_and_unrelated_human_cannot_operate(server, owner_token) -> None:
    client, _settings, _app = server
    await client.post(
        f"{API}/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "DEMO"}
    )
    manager_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", manager_id, ["worker"])
    manager_pat = await login_pat(client, "tl")
    agent_id = await create_agent(client, manager_pat, "dev")
    sibling_id = await create_agent(client, manager_pat, "dev2")
    sibling_pat = await login_pat(client, "tl", act_as_user_id=sibling_id)

    other_id = await create_human(client, owner_token, "other")
    await add_to_project(client, owner_token, "DEMO", other_id, ["worker"])
    other_pat = await login_pat(client, "other")

    task = await _create_task(client, owner_token, title="owned by dev", assignee=agent_id)

    # A sibling agent sharing the same manager does not inherit the assignment.
    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "title": "sibling edit"},
        headers=auth(sibling_pat),
    )
    assert r.status_code == 403, r.text

    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "title": "other edit"},
        headers=auth(other_pat),
    )
    assert r.status_code == 403, r.text

    # The manager may claim an unassigned item directly for its agent; an
    # unrelated member cannot assign it to that agent.
    unassigned = await _create_task(client, owner_token, title="unassigned")
    r = await client.post(
        f"{API}/work-items/{unassigned['display_id']}/assign",
        json={"member": agent_id},
        headers=auth(other_pat),
    )
    assert r.status_code == 403, r.text
    r = await client.post(
        f"{API}/work-items/{unassigned['display_id']}/assign",
        json={"member": agent_id},
        headers=auth(manager_pat),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assignee"]["id"] == agent_id


async def test_task_mode_step_agent_executor_operated_by_manager(
    server, owner_token, monkeypatch
) -> None:
    """A task-mode step may pick an agent executor for a non-DONE target.

    The managing human completes the child task on the agent's behalf; the
    parent step advances with the human as the event actor.
    """
    raw = pyjson5.loads(load_spec_text())
    # task uses the named task_standard definition, so mutate the definition.
    raw["workflow_defs"]["task_standard"]["steps"]["IN_PROGRESS"].append(
        {
            "key": "AGENT_TASK",
            "name": "Agent 任务",
            "to": "TO_REVIEW",
            "mode": "task",
            "actors": ["assignee"],
            "executors": {"min": 1, "max": 1},
            # code_review has its own steps, so adding this task-mode step to
            # the base task workflow does not recurse into itself.
            "tasks": {
                "type": "code_review",
                "title": "子任务 {display_id}",
                "complete_on": "CANCELLED",
            },
        }
    )
    engine = WorkflowEngine(WorkflowSpec.model_validate(raw))
    monkeypatch.setattr(step_service_module, "load_engine", lambda: engine)
    monkeypatch.setattr(workitem_service_module, "load_engine", lambda: engine)

    client, _settings, _app = server
    await client.post(
        f"{API}/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "DEMO"}
    )
    human_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", human_id, ["worker"])
    human_pat = await login_pat(client, "tl")
    agent_id = await create_agent(client, human_pat, "dev")

    task = await _create_task(client, owner_token, title="parent", assignee=agent_id)
    task = (await _move(client, human_pat, task, "IN_PROGRESS")).json()["data"]

    # The human manager starts the task-mode step and names the agent executor.
    r = await client.post(
        f"{API}/work-items/{task['display_id']}/steps/AGENT_TASK",
        json={"row_version": task["row_version"], "executors": [agent_id]},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    assert active is not None
    assert active["executors"][0]["user"]["id"] == agent_id

    detail = (
        await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(owner_token))
    ).json()
    child = detail["meta"]["children"][0]
    assert child["assignee"]["id"] == agent_id

    # Completing the child as the manager marks the agent executor done.
    r = await _move(client, human_pat, child, "CANCELLED")
    assert r.status_code == 200, r.text

    detail = (
        await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(owner_token))
    ).json()
    assert detail["data"]["status"] == "TO_REVIEW"
    assert detail["meta"]["active_step"] is None

    history = (
        await client.get(
            f"{API}/work-items/{task['display_id']}/history", headers=auth(owner_token)
        )
    ).json()["data"]
    executed = next(entry for entry in history if entry["action"] == "step_executed")
    assert executed["actor"]["name"] == "tl"
    assert executed["meta"]["user"]["name"] == "dev"
    completed = next(entry for entry in history if entry["action"] == "step_completed")
    assert completed["actor"]["name"] == "tl"


async def test_manager_closes_code_review_for_agent(server, owner_token) -> None:
    """The reported RDM-4 shape: assignee agent, no reviewers.

    The agent is a DONE candidate, so the human manager can start CODE_REVIEW
    and execute it on the agent's behalf; both identities can close DONE.
    """
    client, _settings, _app = server
    await client.post(
        f"{API}/projects", headers=auth(owner_token), json={"key": "DEMO", "name": "DEMO"}
    )
    human_id = await create_human(client, owner_token, "tl")
    await add_to_project(client, owner_token, "DEMO", human_id, ["worker"])
    human_pat = await login_pat(client, "tl")
    agent_id = await create_agent(client, human_pat, "dev")

    task = await _create_task(client, owner_token, title="review me", assignee=agent_id)
    task = (await _move(client, human_pat, task, "IN_PROGRESS")).json()["data"]
    task = (await _move(client, human_pat, task, "TO_REVIEW")).json()["data"]

    r = await client.patch(
        f"{API}/work-items/{task['display_id']}",
        json={"row_version": task["row_version"], "review_content_md": "done"},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    task = r.json()["data"]

    detail = (
        await client.get(f"{API}/work-items/{task['display_id']}", headers=auth(human_pat))
    ).json()
    code_review = next(
        step for step in detail["meta"]["available_steps"] if step["key"] == "CODE_REVIEW"
    )
    assert [candidate["id"] for candidate in code_review["candidates"]] == [agent_id]
    assert code_review["can_start"] is True

    r = await client.post(
        f"{API}/work-items/{task['display_id']}/steps/CODE_REVIEW",
        json={"row_version": task["row_version"]},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    active = r.json()["meta"]["active_step"]
    assert active is not None
    assert active["executors"][0]["user"]["id"] == agent_id
    assert active["can_execute"] is True

    r = await client.post(
        f"{API}/work-item-steps/{active['id']}/execute",
        json={"note_md": "manager reviewed"},
        headers=auth(human_pat),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "DONE"

    history = (
        await client.get(
            f"{API}/work-items/{task['display_id']}/history", headers=auth(owner_token)
        )
    ).json()["data"]
    executed = next(entry for entry in history if entry["action"] == "step_executed")
    assert executed["actor"]["name"] == "tl"
    assert executed["meta"]["user"]["name"] == "dev"
