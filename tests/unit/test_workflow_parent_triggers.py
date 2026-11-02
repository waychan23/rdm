"""Unit: child-set triggers, inheritance and v4 persistence (§17.137–143)."""

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
            "task_types": ["frontend", "backend", "fullstack"],
            "any": {"statuses": ["IN_PROGRESS"]},
        },
        "parent": {"from": ["TODO"], "to": "IN_PROGRESS"},
    },
    {
        "when": {"any": {"statuses": ["DONE"]}},
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


def test_when_quantifies_the_parents_children() -> None:
    trigger = _spec().resolve("task").parent_triggers[0]
    assert trigger.when.any is not None
    assert trigger.when.any.matches("IN_PROGRESS", False)
    assert not trigger.when.any.matches("DONE", True)
    assert trigger.when.selects("task", "fullstack")
    assert not trigger.when.selects("task", "testing")
    assert not trigger.when.selects("issue", None)


def test_v4_roundtrip_keeps_parent_triggers() -> None:
    assert latest_schema_version() == 4
    resolved = _spec().resolve("task", "fullstack")
    payload = serialize_definition(resolved, schema_version=4)

    assert payload["format"] == 4
    when = payload["parent_triggers"][0]["when"]
    assert when["task_types"] == ["frontend", "backend", "fullstack"]
    assert when["any"] == {"statuses": ["IN_PROGRESS"], "terminal": None}
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


def test_unknown_task_type_is_rejected() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = [
        {
            "when": {"task_types": ["mystery"], "any": {"statuses": ["DONE"]}},
            "parent": {"to": "DONE"},
        }
    ]
    with pytest.raises(PydanticValidationError, match="unknown task types"):
        WorkflowSpec.model_validate(raw)


CHILD_TRIGGERS = [
    {
        "when": {
            "kinds": ["task"],
            "task_types": ["frontend", "fullstack"],
            "any": {"statuses": ["IN_PROGRESS"]},
        },
        "self": {"from": ["TODO"], "to": "IN_PROGRESS"},
    },
    {
        "when": {"kinds": ["task", "issue"], "all": {"terminal": True}},
        "self": {"from": ["TO_TEST"], "to": "DONE"},
    },
]


def _spec_with_child_triggers() -> WorkflowSpec:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = copy.deepcopy(CHILD_TRIGGERS)
    return WorkflowSpec.model_validate(raw)


def test_child_triggers_select_different_child_kinds_and_subtypes() -> None:
    story = _spec_with_child_triggers().resolve("story")
    first, aggregate = story.child_triggers

    assert first.when.selects("task", "frontend")
    assert not first.when.selects("task", "testing")
    assert not first.when.selects("issue", None)
    assert first.when.any is not None and first.when.any.matches("IN_PROGRESS", False)
    assert aggregate.when.all is not None and aggregate.when.all.terminal is True
    assert aggregate.self_.to == "DONE"


def test_child_triggers_inherit_from_kind_and_can_be_cleared() -> None:
    raw = _raw()
    raw["kinds"]["task"]["child_triggers"] = [
        {"when": {"any": {"terminal": True}}, "self": {"to": "DONE"}}
    ]
    raw["kinds"]["task"]["subtypes"]["code_review"]["child_triggers"] = []
    spec = WorkflowSpec.model_validate(raw)

    assert len(spec.resolve("task").child_triggers) == 1
    assert spec.resolve("task", "code_review").child_triggers == ()


def test_v4_roundtrip_keeps_child_triggers() -> None:
    resolved = _spec_with_child_triggers().resolve("story")
    payload = serialize_definition(resolved, schema_version=4)

    assert payload["child_triggers"][0]["when"]["kinds"] == ["task"]
    assert payload["child_triggers"][1]["self"] == {"from": ["TO_TEST"], "to": "DONE"}
    aggregate_when = payload["child_triggers"][1]["when"]
    assert aggregate_when["all"]["terminal"] is True
    assert aggregate_when["any"] is None

    restored = deserialize_definition("story", None, payload)
    assert restored.child_triggers == resolved.child_triggers
    assert serialize_definition(restored, schema_version=4) == payload
    assert "child_triggers" not in serialize_definition(resolved, schema_version=3)


def test_child_trigger_self_state_must_exist() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"any": {"terminal": True}}, "self": {"to": "NOPE"}}
    ]
    with pytest.raises(PydanticValidationError, match="self states"):
        WorkflowSpec.model_validate(raw)


def test_child_trigger_unknown_kind_is_rejected() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"kinds": ["mystery"], "any": {"terminal": True}}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown child kinds"):
        WorkflowSpec.model_validate(raw)


def test_child_trigger_task_types_require_task_kind() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {
                "kinds": ["issue"],
                "task_types": ["frontend"],
                "any": {"terminal": True},
            },
            "self": {"to": "DONE"},
        }
    ]
    with pytest.raises(
        PydanticValidationError, match="requires kinds to be empty or include 'task'"
    ):
        WorkflowSpec.model_validate(raw)


def test_children_any_all_predicates() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {
                "kinds": ["task"],
                "any": {"statuses": ["DONE"], "terminal": True},
                "all": {"statuses": ["DONE"]},
            },
            "self": {"to": "DONE"},
        }
    ]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert when.any is not None and when.any.matches("DONE", True)
    assert not when.any.matches("IN_PROGRESS", False)
    assert when.all is not None and when.all.matches("DONE", True)
    assert not when.all.matches("CANCELLED", True)
    # The quantifier only looks at the selected kinds.
    assert when.selects("task", "frontend")
    assert not when.selects("issue", None)


def test_children_condition_round_trip() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {
                "kinds": ["task"],
                "task_types": ["frontend"],
                "any": {"terminal": True},
                "min_terminal": 2,
            },
            "self": {"to": "DONE"},
        }
    ]
    resolved = WorkflowSpec.model_validate(raw).resolve("story")
    when = resolved.child_triggers[0].when
    assert when.any is not None and when.any.terminal is True
    assert when.min_terminal == 2

    payload = serialize_definition(resolved, schema_version=4)
    stored = payload["child_triggers"][0]["when"]
    assert stored["kinds"] == ["task"]
    assert stored["task_types"] == ["frontend"]
    assert stored["any"]["terminal"] is True
    assert stored["min_terminal"] == 2
    assert deserialize_definition("story", None, payload).child_triggers == resolved.child_triggers


def test_when_requires_a_quantifier() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"kinds": ["task"]}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="when requires"):
        WorkflowSpec.model_validate(raw)


def test_min_terminal_must_be_positive() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"min_terminal": 0}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(raw)


def test_legacy_children_flags_migrate_to_when() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "all_children_terminal": True,
            "min_children_terminal": 2,
            "self": {"to": "DONE"},
        }
    ]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert when.all is not None and when.all.terminal is True
    assert when.min_terminal == 2


def test_legacy_children_block_migrates_to_when() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "children": {"kinds": ["task"], "any": {"terminal": True}},
            "self": {"to": "DONE"},
        }
    ]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert when.kinds == ("task",)
    assert when.any is not None and when.any.terminal is True


def test_legacy_event_when_is_rejected() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"kinds": ["task"], "to": "DONE"}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="children quantifier"):
        WorkflowSpec.model_validate(raw)


def test_legacy_when_any_all_lists_are_rejected() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"any": [{"kinds": ["task"]}]}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="not clause lists"):
        WorkflowSpec.model_validate(raw)


def test_on_error_defaults_to_fail_and_accepts_ignore() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = [
        {"when": {"any": {"statuses": ["IN_PROGRESS"]}}, "parent": {"to": "IN_PROGRESS"}},
        {"when": {"any": {"statuses": ["DONE"]}}, "parent": {"to": "DONE"}, "on_error": "ignore"},
    ]
    resolved = WorkflowSpec.model_validate(raw).resolve("task")
    assert resolved.parent_triggers[0].on_error == "fail"
    assert resolved.parent_triggers[1].on_error == "ignore"

    payload = serialize_definition(resolved, schema_version=4)
    assert payload["parent_triggers"][0]["on_error"] == "fail"
    assert payload["parent_triggers"][1]["on_error"] == "ignore"
    assert deserialize_definition("task", None, payload).parent_triggers == resolved.parent_triggers


def test_on_error_rejects_unknown_policy() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["parent_triggers"] = [
        {"when": {"any": {"statuses": ["DONE"]}}, "parent": {"to": "DONE"}, "on_error": "warn"}
    ]
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(raw)
