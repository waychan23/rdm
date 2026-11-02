"""Unit: parent/child trigger schema, inheritance and v4 persistence (§17.137–138)."""

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
            "to": "IN_PROGRESS",
            "task_types": ["frontend", "backend", "fullstack"],
        },
        "parent": {"from": ["TODO"], "to": "IN_PROGRESS"},
    },
    {
        "when": {"to": "DONE"},
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
        {"when": {"to": "NOPE"}, "parent": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown child states"):
        WorkflowSpec.model_validate(raw)


def test_task_types_only_valid_for_task_definitions() -> None:
    raw = _raw()
    raw["kinds"]["story"]["parent_triggers"] = [
        {"when": {"to": "IN_PROGRESS", "task_types": ["frontend"]}, "parent": {"to": "DONE"}}
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


CHILD_TRIGGERS = [
    {
        "when": {"kinds": ["task"], "task_types": ["frontend", "fullstack"]},
        "self": {"from": ["TODO"], "to": "IN_PROGRESS"},
    },
    {
        "when": {"kinds": ["task", "issue"]},
        "all_children_terminal": True,
        "self": {"from": ["TO_TEST"], "to": "DONE"},
    },
]


def _spec_with_child_triggers() -> WorkflowSpec:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = copy.deepcopy(CHILD_TRIGGERS)
    return WorkflowSpec.model_validate(raw)


def test_child_triggers_match_different_child_kinds_and_subtypes() -> None:
    story = _spec_with_child_triggers().resolve("story")
    first, aggregate = story.child_triggers

    assert first.when.matches("task", "frontend", "TODO", "IN_PROGRESS")
    assert not first.when.matches("task", "testing", "TODO", "IN_PROGRESS")
    assert not first.when.matches("issue", None, "TODO", "IN_PROGRESS")
    # The aggregate rule matches an issue child just as well as a task child.
    assert aggregate.when.matches("issue", None, "OPEN", "CLOSED_DONE")
    assert aggregate.when.matches("task", "testing", "IN_PROGRESS", "DONE")
    assert aggregate.all_children_terminal is True
    assert aggregate.self_.to == "DONE"


def test_child_triggers_inherit_from_kind_and_can_be_cleared() -> None:
    raw = _raw()
    raw["kinds"]["task"]["child_triggers"] = [{"self": {"to": "DONE"}}]
    raw["kinds"]["task"]["subtypes"]["code_review"]["child_triggers"] = []
    spec = WorkflowSpec.model_validate(raw)

    assert len(spec.resolve("task").child_triggers) == 1
    assert spec.resolve("task", "code_review").child_triggers == ()


def test_v4_roundtrip_keeps_child_triggers() -> None:
    resolved = _spec_with_child_triggers().resolve("story")
    payload = serialize_definition(resolved, schema_version=4)

    assert payload["child_triggers"][0]["when"]["kinds"] == ["task"]
    assert payload["child_triggers"][1]["self"] == {"from": ["TO_TEST"], "to": "DONE"}
    assert payload["child_triggers"][1]["all_children_terminal"] is True

    restored = deserialize_definition("story", None, payload)
    assert restored.child_triggers == resolved.child_triggers
    assert serialize_definition(restored, schema_version=4) == payload
    assert "child_triggers" not in serialize_definition(resolved, schema_version=3)


def test_child_trigger_self_state_must_exist() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [{"self": {"to": "NOPE"}}]
    with pytest.raises(PydanticValidationError, match="self states"):
        WorkflowSpec.model_validate(raw)


def test_child_trigger_unknown_kind_is_rejected() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"kinds": ["mystery"]}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown child kinds"):
        WorkflowSpec.model_validate(raw)


def test_child_trigger_task_types_require_task_kind() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"kinds": ["issue"], "task_types": ["frontend"]},
            "self": {"to": "DONE"},
        }
    ]
    with pytest.raises(PydanticValidationError, match="requires when.kinds to include 'task'"):
        WorkflowSpec.model_validate(raw)


def test_when_any_all_groups_are_and_ed_with_flat_fields() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {
                "kinds": ["task", "issue"],
                "any": [
                    {"kinds": ["task"], "task_types": ["frontend"], "to": "DONE"},
                    {"kinds": ["issue"], "to": "CLOSED_DONE"},
                ],
                "all": [
                    {"from": ["IN_PROGRESS", "FIXING"]},
                    {"kinds": ["task", "issue"]},
                ],
            },
            "self": {"to": "DONE"},
        }
    ]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when

    assert when.matches("task", "frontend", "IN_PROGRESS", "DONE")
    assert when.matches("issue", None, "FIXING", "CLOSED_DONE")
    # any: neither branch matches for a testing task.
    assert not when.matches("task", "testing", "IN_PROGRESS", "DONE")
    # all: the source state is not in every clause.
    assert not when.matches("task", "frontend", "TODO", "DONE")


def test_nested_any_all_groups() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {
                "any": [
                    {"all": [{"kinds": ["task"]}, {"task_types": ["frontend"]}]},
                    {"kinds": ["issue"]},
                ]
            },
            "self": {"to": "DONE"},
        }
    ]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when

    assert when.matches("task", "frontend", "TODO", "IN_PROGRESS")
    assert not when.matches("task", "backend", "TODO", "IN_PROGRESS")
    assert when.matches("issue", None, "OPEN", "CLOSED_DONE")


def test_children_aggregate_fields_round_trip() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"kinds": ["task", "issue"]},
            "any_children_terminal": True,
            "min_children_terminal": 2,
            "self": {"to": "DONE"},
        }
    ]
    resolved = WorkflowSpec.model_validate(raw).resolve("story")
    rule = resolved.child_triggers[0]
    assert rule.any_children_terminal is True
    assert rule.min_children_terminal == 2

    payload = serialize_definition(resolved, schema_version=4)
    assert payload["child_triggers"][0]["any_children_terminal"] is True
    assert payload["child_triggers"][0]["min_children_terminal"] == 2
    assert deserialize_definition("story", None, payload).child_triggers == resolved.child_triggers


def test_min_children_terminal_must_be_positive() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [{"min_children_terminal": 0, "self": {"to": "DONE"}}]
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(raw)


def test_nested_when_groups_are_validated_recursively() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"any": [{"kinds": ["mystery"]}]}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match=r"any\[0\]: unknown child kinds"):
        WorkflowSpec.model_validate(raw)


def test_when_to_accepts_a_legacy_single_item_list() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [{"when": {"to": ["DONE"]}, "self": {"to": "DONE"}}]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert when.to == "DONE"


def test_when_to_rejects_multiple_states() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"to": ["DONE", "CANCELLED"]}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="single state"):
        WorkflowSpec.model_validate(raw)
