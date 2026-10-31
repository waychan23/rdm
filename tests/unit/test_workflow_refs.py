"""Unit tests: named workflow definitions (workflow_defs) and ``use`` refs."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_spec, load_spec_text
from rdm.domain.workflow.schema import WorkflowSpec


def _dev_flow() -> dict:
    return {
        "states": ["TODO", "IN_PROGRESS", "DONE"],
        "initial": "TODO",
        "terminal": ["DONE"],
        "fields": {"reviewer": True},
        "steps": {
            "TODO": [{"key": "START", "name": "开始", "to": "IN_PROGRESS"}],
            "IN_PROGRESS": [{"key": "FINISH", "name": "完成", "to": "DONE"}],
            "DONE": [],
        },
    }


def _testing_flow() -> dict:
    return {
        "states": ["TODO", "TESTING", "DONE"],
        "initial": "TODO",
        "terminal": ["DONE"],
        "steps": {
            "TODO": [{"key": "START", "name": "开始", "to": "TESTING"}],
            "TESTING": [{"key": "PASS", "name": "通过", "to": "DONE"}],
            "DONE": [],
        },
    }


def _spec(**overrides) -> WorkflowSpec:
    data = {
        "version": 3,
        "task_types": {
            "other": "其他",
            "frontend": "前端开发",
            "backend": "后端开发",
            "testing": "测试",
        },
        "workflow_defs": {"dev": _dev_flow(), "qa": _testing_flow()},
        "kinds": {"task": {"use": "dev"}},
    }
    data.update(overrides)
    return WorkflowSpec.model_validate(data)


def test_kind_can_use_named_definition() -> None:
    spec = _spec()
    resolved = spec.resolve("task")
    assert resolved.states == ("TODO", "IN_PROGRESS", "DONE")
    assert resolved.initial == "TODO"
    assert resolved.terminal == ("DONE",)
    assert resolved.fields.reviewer is True
    assert [step.key for step in resolved.steps_from("IN_PROGRESS")] == ["FINISH"]


def test_referenced_definition_is_expanded_in_place() -> None:
    spec = _spec()
    kind = spec.kinds["task"]
    # Downstream code only sees the resolved graph, never a dangling ref.
    assert kind.states == ("TODO", "IN_PROGRESS", "DONE")
    assert "use" not in kind.model_dump()


def test_multiple_subtypes_share_one_definition() -> None:
    spec = _spec(
        kinds={
            "task": {
                "use": "dev",
                "subtypes": {
                    "frontend": {"use": "dev"},
                    "backend": {"use": "dev"},
                    "testing": {"use": "qa"},
                },
            }
        }
    )
    base = spec.resolve("task")
    frontend = spec.resolve("task", "frontend")
    backend = spec.resolve("task", "backend")
    assert frontend.states == backend.states and frontend.steps == backend.steps
    assert frontend.steps == base.steps
    assert spec.resolve("task", "testing").states == ("TODO", "TESTING", "DONE")


def test_local_keys_override_definition() -> None:
    spec = _spec(
        kinds={
            "task": {
                "use": "dev",
                "label": "开发任务",
                "label_en": "Dev task",
                "fields": {"reviewer": True, "review_content": True},
            }
        }
    )
    resolved = spec.resolve("task")
    assert resolved.label == "开发任务"
    assert resolved.label_en == "Dev task"
    assert resolved.fields.review_content is True


def test_use_cannot_be_combined_with_inline_graph() -> None:
    with pytest.raises(PydanticValidationError, match="cannot declare states"):
        _spec(kinds={"task": {"use": "dev", "states": ["TODO", "DONE"]}})


def test_unknown_reference_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="unknown workflow_defs reference 'nope'"):
        _spec(kinds={"task": {"use": "nope"}})


def test_definitions_cannot_reference_other_definitions() -> None:
    with pytest.raises(PydanticValidationError, match="cannot reference other definitions"):
        _spec(
            workflow_defs={
                "dev": _dev_flow(),
                "alias": {"use": "dev"},
            }
        )


def test_invalid_definition_reports_its_name() -> None:
    broken = _dev_flow()
    broken["steps"].pop("DONE")
    with pytest.raises(PydanticValidationError, match="workflow_defs.broken is invalid"):
        _spec(workflow_defs={"broken": broken})


def test_definition_name_must_be_filename_safe() -> None:
    with pytest.raises(PydanticValidationError, match="must match"):
        _spec(workflow_defs={"Dev Flow": _dev_flow()})


def test_engine_runs_steps_from_referenced_definition() -> None:
    engine = WorkflowEngine(_spec())
    assert engine.allowed("task", "TODO") == ("IN_PROGRESS",)
    step = engine.resolve_step("task", "TODO", key="START")
    assert step.to == "IN_PROGRESS"


def test_packaged_spec_uses_named_definition_for_task() -> None:
    spec = load_spec()
    assert "task_standard" in spec.workflow_defs
    assert "use:" in load_spec_text().split("workflow_defs", 1)[1]
    resolved = spec.resolve("task")
    assert "TO_REVIEW" in resolved.states
    assert [step.key for step in resolved.steps_from("TO_REVIEW")][0] == "CODE_REVIEW"
