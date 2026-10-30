"""Unit tests: workflow v3 named steps, executor modes, fields and gates."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from rdm.domain.errors import WorkflowGateBlocked, WorkflowIllegalTransition
from rdm.domain.workflow.engine import GateContext, WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec


def _spec(kinds: dict, task_types: dict | None = None) -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {
            "version": 3,
            "task_types": task_types or {"other": "其他"},
            "kinds": kinds,
        }
    )


def _task_kind(**overrides) -> dict:
    data = {
        "states": ["TODO", "TO_REVIEW", "DONE"],
        "initial": "TODO",
        "terminal": ["DONE"],
        "fields": {"reviewer": True, "review_content": True},
        "steps": {
            "TODO": [{"key": "START", "name": "开始", "to": "TO_REVIEW"}],
            "TO_REVIEW": [
                {
                    "key": "CODE_REVIEW",
                    "name": "Code Review",
                    "to": "DONE",
                    "mode": "approval",
                    "actors": ["reviewers"],
                    "executors": {"min": 1, "max": 2},
                    "note": "required",
                    "gates": {"required_fields": ["reviewer", "review_content"]},
                }
            ],
            "DONE": [],
        },
    }
    data.update(overrides)
    return data


def test_legacy_transitions_are_normalized_into_steps() -> None:
    spec = _spec(
        {
            "task": {
                "states": ["A", "B"],
                "initial": "A",
                "terminal": ["B"],
                "transitions": {"A": ["B"], "B": []},
            }
        }
    )
    engine = WorkflowEngine(spec)
    assert engine.allowed("task", "A") == ("B",)
    step = engine.resolve_step("task", "A", dst="B")
    assert step.key == "TO_B"
    assert step.mode == "direct"


def test_ambiguous_target_requires_step_key() -> None:
    kind = _task_kind()
    kind["steps"]["TO_REVIEW"].append({"key": "QUICK_DONE", "name": "快速完成", "to": "DONE"})
    engine = WorkflowEngine(_spec({"task": kind}))
    with pytest.raises(WorkflowIllegalTransition) as exc:
        engine.resolve_step("task", "TO_REVIEW", dst="DONE")
    assert {s["key"] for s in exc.value.details["available_steps"]} == {
        "CODE_REVIEW",
        "QUICK_DONE",
    }
    step = engine.resolve_step("task", "TO_REVIEW", dst="DONE", key="QUICK_DONE")
    assert step.key == "QUICK_DONE"


def test_required_fields_gate_blocks_and_passes() -> None:
    engine = WorkflowEngine(_spec({"task": _task_kind()}))
    with pytest.raises(WorkflowGateBlocked) as exc:
        engine.check(
            "task",
            "TO_REVIEW",
            "DONE",
            item="RDM-1",
            context=GateContext(field_values={"reviewer": [], "review_content": "  "}),
        )
    missing = exc.value.details["missing_fields"]
    assert {m["key"] for m in missing} == {"reviewer", "review_content"}

    engine.check(
        "task",
        "TO_REVIEW",
        "DONE",
        item="RDM-1",
        context=GateContext(field_values={"reviewer": ["u1"], "review_content": "LGTM"}),
    )


def test_step_gate_merges_kind_default_fieldwise() -> None:
    kind = _task_kind()
    kind["gates"] = {"DONE": {"children_all_terminal": True}}
    engine = WorkflowEngine(_spec({"task": kind}))
    step = engine.resolve_step("task", "TO_REVIEW", dst="DONE")
    gate = engine.effective_gate("task", "TO_REVIEW", step)
    assert gate is not None
    assert gate.children_all_terminal is True
    assert gate.required_fields == ("reviewer", "review_content")


def test_direct_mode_requires_single_executor() -> None:
    kind = _task_kind()
    kind["steps"]["TO_REVIEW"][0] = {
        "key": "BAD",
        "name": "坏步骤",
        "to": "DONE",
        "mode": "direct",
        "executors": {"min": 1, "max": 2},
    }
    with pytest.raises(PydanticValidationError):
        _spec({"task": kind})


def _child_subtype() -> dict:
    return {
        "label": "Code Review",
        "states": ["TODO", "DONE"],
        "initial": "TODO",
        "terminal": ["DONE"],
        "steps": {
            "TODO": [{"key": "FINISH", "name": "完成", "to": "DONE"}],
            "DONE": [],
        },
    }


def test_task_mode_requires_tasks_and_optional_note() -> None:
    kind = _task_kind()
    kind["subtypes"] = {"code_review": _child_subtype()}
    kind["steps"]["TO_REVIEW"][0] = {
        "key": "TASKS",
        "name": "子任务",
        "to": "DONE",
        "mode": "task",
        "note": "required",
        "tasks": {"type": "code_review"},
    }
    with pytest.raises(PydanticValidationError):
        _spec(
            {"task": kind},
            task_types={"other": "其他", "code_review": "代码评审"},
        )

    kind["steps"]["TO_REVIEW"][0]["note"] = "optional"
    _spec(
        {"task": kind},
        task_types={"other": "其他", "code_review": "代码评审"},
    )


def test_task_mode_complete_on_must_be_terminal() -> None:
    kind = _task_kind()
    kind["subtypes"] = {"code_review": _child_subtype()}
    kind["steps"]["TO_REVIEW"][0] = {
        "key": "TASKS",
        "name": "子任务",
        "to": "DONE",
        "mode": "task",
        "tasks": {"type": "code_review", "complete_on": "TODO"},
    }
    with pytest.raises(PydanticValidationError):
        _spec(
            {"task": kind},
            task_types={"other": "其他", "code_review": "代码评审"},
        )


def test_subtype_can_define_its_own_state_graph() -> None:
    task = _task_kind()
    task["subtypes"] = {
        "other": {
            "label": "Other",
            "states": ["NEW", "DONE"],
            "initial": "NEW",
            "terminal": ["DONE"],
            "steps": {
                "NEW": [{"key": "FINISH", "name": "完成", "to": "DONE"}],
                "DONE": [],
            },
            "fields": {"custom": [{"key": "note", "label": "备注", "type": "text"}]},
        }
    }
    spec = _spec({"task": task}, task_types={"other": "其他"})
    engine = WorkflowEngine(spec)
    assert engine.initial_status("task") == "TODO"
    assert engine.initial_status("task", "other") == "NEW"
    resolved = engine.resolve("task", "other")
    assert resolved.states == ("NEW", "DONE")
    assert resolved.fields.custom[0].key == "note"
    assert resolved.fields.reviewer is True  # inherited from task


def test_subtype_declaring_states_must_declare_all_steps() -> None:
    task = _task_kind()
    task["subtypes"] = {
        "other": {
            "states": ["NEW", "DONE"],
            "initial": "NEW",
            "terminal": ["DONE"],
            "steps": {"NEW": [{"key": "FINISH", "name": "完成", "to": "DONE"}]},
        }
    }
    with pytest.raises(PydanticValidationError):
        _spec({"task": task}, task_types={"other": "其他"})


def test_required_field_must_be_enabled() -> None:
    kind = _task_kind()
    kind["fields"] = {"reviewer": False, "review_content": False}
    with pytest.raises(PydanticValidationError):
        _spec({"task": kind})
