"""Unit: parent-trigger schema, inheritance and v4 persistence (§17.137)."""

from __future__ import annotations

import copy

import pyjson5
import pytest
from pydantic import ValidationError as PydanticValidationError

from rdm.domain.workflow.schema import WorkflowSpec
from rdm.domain.workflow.schema_versions import latest_schema_version
from rdm.domain.workflow.versioning import deserialize_definition, serialize_definition
from tests.workflow_support import load_test_spec_text

TRIGGERS = [
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
]


def _raw() -> dict:
    raw = pyjson5.loads(load_test_spec_text())
    raw["version"] = 4
    return raw


def _spec() -> WorkflowSpec:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = copy.deepcopy(TRIGGERS)
    return WorkflowSpec.model_validate(raw)


def test_triggers_inherit_from_kind_and_can_be_cleared_by_subtype() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = copy.deepcopy(TRIGGERS)
    raw["kinds"]["task"]["subtypes"]["code_review"]["parent_triggers"] = []
    spec = WorkflowSpec.model_validate(raw)

    assert len(spec.resolve("task").parent_triggers) == 2
    assert len(spec.resolve("task", "fullstack").parent_triggers) == 2
    # code_review declares an explicit empty list to opt out of the rules.
    assert spec.resolve("task", "code_review").parent_triggers == ()


def test_when_matcher_uses_child_states_and_task_types() -> None:
    trigger = _spec().resolve("task").parent_triggers[0]
    assert trigger.when.matches("TODO", "IN_PROGRESS", "fullstack")
    assert not trigger.when.matches("TODO", "IN_PROGRESS", "testing")
    assert not trigger.when.matches("IN_PROGRESS", "TO_REVIEW", "fullstack")
    # The second rule has no task-type restriction.
    assert _spec().resolve("task").parent_triggers[1].when.matches("TO_REVIEW", "DONE", "testing")


def test_v4_roundtrip_keeps_parent_triggers() -> None:
    assert latest_schema_version() == 4
    resolved = _spec().resolve("task", "fullstack")
    payload = serialize_definition(resolved, schema_version=4)

    assert payload["format"] == 4
    assert payload["parent_triggers"][0]["when"]["from"] == ["TODO"]
    assert payload["parent_triggers"][0]["when"]["task_types"] == [
        "frontend",
        "backend",
        "fullstack",
    ]
    assert payload["parent_triggers"][0]["parent"] == {
        "from": ["TODO"],
        "to": "IN_PROGRESS",
    }

    restored = deserialize_definition("task", "fullstack", payload)
    assert restored.parent_triggers == resolved.parent_triggers
    assert serialize_definition(restored, schema_version=4) == payload


def test_v3_payload_stays_historical_without_triggers() -> None:
    payload = serialize_definition(_spec().resolve("task"), schema_version=3)
    assert payload["format"] == 3
    assert "parent_triggers" not in payload


def test_unknown_child_state_is_rejected() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = [
        {"when": {"to": ["NOPE"]}, "parent": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown child states"):
        WorkflowSpec.model_validate(raw)


def test_task_types_only_valid_for_task_definitions() -> None:
    raw = _raw()
    raw["kinds"]["story"]["parent_triggers"] = [
        {"when": {"to": ["IN_PROGRESS"], "task_types": ["frontend"]}, "parent": {"to": "DONE"}}
    ]
    with pytest.raises(
        PydanticValidationError, match="task_types is only valid for task definitions"
    ):
        WorkflowSpec.model_validate(raw)


def test_unknown_task_type_is_rejected() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = [
        {"when": {"task_types": ["mystery"]}, "parent": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown task types"):
        WorkflowSpec.model_validate(raw)
