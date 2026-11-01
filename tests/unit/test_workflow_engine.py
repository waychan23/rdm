"""Unit tests: workflow engine transition table + gates (plan M0-3)."""

import pytest

from rdm.domain.errors import ValidationError, WorkflowGateBlocked, WorkflowIllegalTransition
from rdm.domain.workflow.engine import GateChild, GateContext, GateSprintItem, WorkflowEngine
from rdm.domain.workflow.loader import load_engine, load_spec


@pytest.fixture(scope="module")
def engine() -> WorkflowEngine:
    return load_engine()


def test_spec_has_all_kinds_and_version() -> None:
    spec = load_spec()
    assert spec.version == 3
    assert set(spec.kinds) == {"epic", "story", "issue", "task", "sprint"}


def test_initial_and_terminal_states(engine: WorkflowEngine) -> None:
    assert engine.initial_status("epic") == "TODO"
    assert engine.initial_status("story") == "TODO"
    assert engine.initial_status("issue") == "OPEN"
    assert engine.initial_status("task") == "TODO"
    assert engine.initial_status("sprint") == "PLANNED"
    assert engine.is_terminal("task", "DONE")
    assert engine.is_terminal("sprint", "CLOSED")
    assert not engine.is_terminal("story", "TO_TEST")


def test_happy_path_story(engine: WorkflowEngine) -> None:
    for src, dst in [
        ("TODO", "IN_PROGRESS"),
        ("IN_PROGRESS", "TO_TEST"),
        ("TO_TEST", "DONE"),
        ("DONE", "PUBLISHED"),
    ]:
        ctx = GateContext(children=[GateChild("task", "DONE", "RDM-2")]) if dst == "DONE" else None
        engine.check("story", src, dst, item="RDM-1", context=ctx)


def test_illegal_transition_carries_allowed(engine: WorkflowEngine) -> None:
    with pytest.raises(WorkflowIllegalTransition) as exc:
        engine.check("task", "TODO", "DONE")
    err = exc.value
    assert err.details["from"] == "TODO"
    assert err.details["to"] == "DONE"
    assert err.details["allowed_transitions"] == ["IN_PROGRESS", "CANCELLED"]


def test_terminal_states_have_no_or_only_named_exits(engine: WorkflowEngine) -> None:
    # task DONE is frozen; CANCELLED is frozen.
    assert engine.allowed("task", "DONE") == ()
    assert engine.allowed("task", "CANCELLED") == ()
    with pytest.raises(WorkflowIllegalTransition):
        engine.check("task", "CANCELLED", "TODO")
    # story DONE may only publish.
    assert engine.allowed("story", "DONE") == ("PUBLISHED",)
    # issue terminal CLOSED_DONE allows REOPEN explicitly.
    assert engine.allowed("issue", "CLOSED_DONE") == ("REOPEN",)


def test_issue_first_fix_can_close_v2(engine: WorkflowEngine) -> None:
    # workflow v2 (architecture §16.35): FIXING may enter CLOSED_DONE
    # directly, but the min_children gate still applies.
    with pytest.raises(WorkflowGateBlocked) as exc:
        engine.check("issue", "FIXING", "CLOSED_DONE", item="RDM-9", context=GateContext())
    assert exc.value.details["min_children"] == 1
    ctx = GateContext(children=[GateChild("task", "DONE", "RDM-10")])
    engine.check("issue", "FIXING", "CLOSED_DONE", item="RDM-9", context=ctx)


def test_issue_reopen_flow(engine: WorkflowEngine) -> None:
    engine.check("issue", "CLOSED_DONE", "REOPEN")
    engine.check("issue", "REOPEN", "FIXING")
    # REOPEN may also re-close directly.
    ctx = GateContext(children=[GateChild("task", "DONE", "RDM-10")])
    engine.check("issue", "REOPEN", "CLOSED_DONE", item="RDM-9", context=ctx)


def test_story_gate_blocks_on_open_children(engine: WorkflowEngine) -> None:
    ctx = GateContext(
        children=[
            GateChild("task", "DONE", "RDM-2"),
            GateChild("task", "IN_PROGRESS", "RDM-3"),
        ]
    )
    with pytest.raises(WorkflowGateBlocked) as exc:
        engine.check("story", "TO_TEST", "DONE", item="RDM-1", context=ctx)
    details = exc.value.details
    assert details["blocking_children"] == ["RDM-3"]
    assert details["target"] == "DONE"
    assert "allowed_transitions" in details and details["hint"]


def test_story_gate_passes_when_all_children_terminal(engine: WorkflowEngine) -> None:
    ctx = GateContext(
        children=[GateChild("task", "DONE", "RDM-2"), GateChild("task", "CANCELLED", "RDM-3")]
    )
    engine.check("story", "TO_TEST", "DONE", item="RDM-1", context=ctx)


def test_epic_gate_publish(engine: WorkflowEngine) -> None:
    with pytest.raises(WorkflowGateBlocked):
        engine.check(
            "epic",
            "IN_PROGRESS",
            "DONE",
            item="RDM-1",
            context=GateContext(children=[GateChild("story", "IN_PROGRESS", "RDM-2")]),
        )


def test_issue_gate_requires_min_children(engine: WorkflowEngine) -> None:
    # Per shipped workflow, CLOSED_DONE is entered from the REOPEN state.
    with pytest.raises(WorkflowGateBlocked) as exc:
        engine.check(
            "issue", "REOPEN", "CLOSED_DONE", item="RDM-9", context=GateContext(children=[])
        )
    assert exc.value.details["min_children"] == 1
    assert exc.value.details["child_count"] == 0


def test_issue_gate_passes_with_terminal_fix_task(engine: WorkflowEngine) -> None:
    ctx = GateContext(children=[GateChild("task", "DONE", "RDM-10")])
    engine.check("issue", "REOPEN", "CLOSED_DONE", item="RDM-9", context=ctx)


def test_sprint_gate_blocks_on_nonterminal_items(engine: WorkflowEngine) -> None:
    ctx = GateContext(
        sprint_items=[
            GateSprintItem("story", "DONE", "RDM-1"),
            GateSprintItem("task", "TO_REVIEW", "RDM-2"),
        ]
    )
    with pytest.raises(WorkflowGateBlocked) as exc:
        engine.check("sprint", "ACTIVE", "CLOSED", item="Sprint-1", context=ctx)
    assert exc.value.details["blocking_children"] == ["RDM-2"]


def test_sprint_gate_passes_when_items_terminal(engine: WorkflowEngine) -> None:
    ctx = GateContext(sprint_items=[GateSprintItem("task", "DONE", "RDM-2")])
    engine.check("sprint", "ACTIVE", "CLOSED", item="Sprint-1", context=ctx)


def test_task_code_review_step_open_to_project_members(engine: WorkflowEngine) -> None:
    # Dev subtypes use the review flow: CODE_REVIEW is an approval step open to
    # any project member, and the shipped config no longer requires
    # review_content, so an empty context passes the step's field gate.
    step = engine.resolve_step("task", "TO_REVIEW", key="CODE_REVIEW", task_type="backend")
    assert step.mode == "approval"
    assert step.actors == ("assignee", "project_members")
    engine.check(
        "task",
        "TO_REVIEW",
        "DONE",
        context=GateContext(children=[]),
        step_key="CODE_REVIEW",
        task_type="backend",
    )


def test_unknown_kind_and_state(engine: WorkflowEngine) -> None:
    with pytest.raises(ValidationError):
        engine.allowed("bug", "TODO")
    with pytest.raises(ValidationError):
        engine.allowed("task", "WAT")
