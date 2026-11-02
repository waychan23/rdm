"""Unit: trigger rules (trigger + when + action) and v4 persistence (§17.137–145)."""

from __future__ import annotations

import copy

import pyjson5
import pytest
from pydantic import ValidationError as PydanticValidationError

from rdm.domain.workflow.schema import StatusFlags, WorkflowSpec
from rdm.domain.workflow.schema_versions import latest_schema_version
from rdm.domain.workflow.versioning import deserialize_definition, serialize_definition
from tests.workflow_support import load_test_spec_text


def _flags(
    *,
    start: bool = False,
    terminal: bool = False,
    main_terminal: bool = False,
    side_terminal: bool = False,
) -> StatusFlags:
    return StatusFlags(
        start=start,
        terminal=terminal,
        main_terminal=main_terminal,
        side_terminal=side_terminal,
    )


TRIGGERS = [
    {
        "trigger": {
            "kinds": ["task"],
            "tasktypes": ["frontend", "backend", "fullstack"],
            "from": ["TODO"],
            "to": "IN_PROGRESS",
        },
        "when": {
            "any": {
                "kinds": ["task"],
                "tasktypes": ["frontend", "backend", "fullstack"],
                "statuses": ["IN_PROGRESS"],
            }
        },
        "parent": {"from": ["TODO"], "to": "IN_PROGRESS"},
    },
    {
        "trigger": {"to": "DONE"},
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


def test_trigger_matches_the_changed_child_event() -> None:
    trigger = _spec().resolve("task").parent_triggers[0].trigger
    assert trigger is not None

    def matches(kind: str, task_type: str | None, old: str, new: str) -> bool:
        return trigger.matches(
            kind,
            task_type,
            old,
            new,
            from_flags=_flags(start=old == "TODO"),
            to_flags=_flags(
                start=new == "TODO",
                terminal=new == "DONE",
                main_terminal=new == "DONE",
            ),
        )

    assert matches("task", "fullstack", "TODO", "IN_PROGRESS")
    assert not matches("task", "testing", "TODO", "IN_PROGRESS")
    assert not matches("issue", None, "TODO", "IN_PROGRESS")
    assert not matches("task", "fullstack", "IN_PROGRESS", "DONE")


def test_when_quantifies_current_child_state() -> None:
    when = _spec().resolve("task").parent_triggers[0].when
    assert when is not None and when.any is not None
    assert when.any.matches("IN_PROGRESS", _flags())
    assert not when.any.matches("DONE", _flags(terminal=True, main_terminal=True))
    assert when.any.selects("task", "fullstack")
    assert not when.any.selects("task", "testing")


def test_start_and_terminal_predicates() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"any": {"kinds": ["task"], "start": False, "terminal": False}},
            "self": {"to": "DONE"},
        }
    ]
    clause = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert clause is not None and clause.any is not None
    assert clause.any.matches("IN_PROGRESS", _flags())
    assert not clause.any.matches("TODO", _flags(start=True))
    assert not clause.any.matches("DONE", _flags(terminal=True, main_terminal=True))


def test_v4_roundtrip_keeps_parent_triggers() -> None:
    assert latest_schema_version() == 4
    resolved = _spec().resolve("task", "fullstack")
    payload = serialize_definition(resolved, schema_version=4)

    assert payload["format"] == 4
    rule = payload["parent_triggers"][0]
    assert rule["trigger"]["kinds"] == ["task"]
    assert rule["trigger"]["tasktypes"] == ["frontend", "backend", "fullstack"]
    assert rule["trigger"]["from"]["statuses"] == ["TODO"]
    assert rule["trigger"]["to"]["statuses"] == ["IN_PROGRESS"]
    assert rule["when"]["any"]["statuses"] == ["IN_PROGRESS"]
    assert rule["parent"]["from"] == ["TODO"]
    assert rule["parent"]["to"] == "IN_PROGRESS"
    assert rule["parent"]["step"] is None

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
        {"trigger": {"tasktypes": ["mystery"]}, "parent": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown task types"):
        WorkflowSpec.model_validate(raw)


CHILD_TRIGGERS = [
    {
        "trigger": {
            "kinds": ["task"],
            "tasktypes": ["frontend", "fullstack"],
            "from": ["TODO"],
            "to": "IN_PROGRESS",
        },
        "when": {
            "any": {
                "kinds": ["task"],
                "tasktypes": ["frontend", "fullstack"],
                "statuses": ["IN_PROGRESS"],
            }
        },
        "self": {"from": ["TODO"], "to": "IN_PROGRESS"},
    },
    {
        "when": {"all": {"kinds": ["task", "issue"], "terminal": True}},
        "self": {"from": ["TO_TEST"], "to": "DONE"},
    },
]


def _spec_with_child_triggers() -> WorkflowSpec:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = copy.deepcopy(CHILD_TRIGGERS)
    return WorkflowSpec.model_validate(raw)


def test_child_triggers_support_trigger_when_and_self() -> None:
    story = _spec_with_child_triggers().resolve("story")
    first, aggregate = story.child_triggers

    assert first.trigger is not None
    assert first.trigger.matches(
        "task",
        "frontend",
        "TODO",
        "IN_PROGRESS",
        from_flags=_flags(start=True),
        to_flags=_flags(),
    )
    assert first.when is not None and first.when.any is not None
    assert first.when.any.selects("task", "frontend")
    assert aggregate.when is not None and aggregate.when.all is not None
    assert aggregate.when.all.terminal is True
    assert aggregate.self_.to == "DONE"


def test_child_triggers_inherit_from_kind_and_can_be_cleared() -> None:
    raw = _raw()
    raw["kinds"]["task"]["child_triggers"] = [
        {"when": {"all": {"terminal": True}}, "self": {"to": "DONE"}}
    ]
    raw["kinds"]["task"]["subtypes"]["code_review"]["child_triggers"] = []
    spec = WorkflowSpec.model_validate(raw)

    assert len(spec.resolve("task").child_triggers) == 1
    assert spec.resolve("task", "code_review").child_triggers == ()


def test_v4_roundtrip_keeps_child_triggers() -> None:
    resolved = _spec_with_child_triggers().resolve("story")
    payload = serialize_definition(resolved, schema_version=4)

    first = payload["child_triggers"][0]
    assert first["trigger"]["tasktypes"] == ["frontend", "fullstack"]
    assert first["when"]["any"]["statuses"] == ["IN_PROGRESS"]
    child_target = payload["child_triggers"][1]["self"]
    assert child_target["from"] == ["TO_TEST"]
    assert child_target["to"] == "DONE"
    assert payload["child_triggers"][1]["when"]["all"]["terminal"] is True

    restored = deserialize_definition("story", None, payload)
    assert restored.child_triggers == resolved.child_triggers
    assert serialize_definition(restored, schema_version=4) == payload
    assert "child_triggers" not in serialize_definition(resolved, schema_version=3)


def test_rule_accepts_trigger_only_or_when_only() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"trigger": {"to": "DONE"}, "self": {"to": "DONE"}},
        {"when": {"any": {"terminal": True}}, "self": {"to": "DONE"}},
    ]
    rules = WorkflowSpec.model_validate(raw).resolve("story").child_triggers
    assert rules[0].trigger is not None and rules[0].when is None
    assert rules[1].trigger is None and rules[1].when is not None


def test_rule_requires_trigger_or_when() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [{"self": {"to": "DONE"}}]
    with pytest.raises(PydanticValidationError, match="requires trigger or when"):
        WorkflowSpec.model_validate(raw)


def test_trigger_tasktypes_require_task_kind() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"trigger": {"kinds": ["issue"], "tasktypes": ["frontend"]}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(
        PydanticValidationError, match="requires kinds to be empty or include 'task'"
    ):
        WorkflowSpec.model_validate(raw)


def test_unknown_kind_in_when_is_rejected() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {"when": {"any": {"kinds": ["mystery"]}}, "self": {"to": "DONE"}}
    ]
    with pytest.raises(PydanticValidationError, match="unknown child kinds"):
        WorkflowSpec.model_validate(raw)


def test_legacy_event_when_and_children_migrate() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"kinds": ["task"], "from": ["TODO"], "to": "DONE"},
            "children": {"kinds": ["task"], "any": {"terminal": True}},
            "self": {"to": "DONE"},
        }
    ]
    rule = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0]
    assert rule.trigger is not None
    assert rule.trigger.matches(
        "task",
        None,
        "TODO",
        "DONE",
        from_flags=_flags(start=True),
        to_flags=_flags(terminal=True, main_terminal=True),
    )
    assert rule.when is not None and rule.when.any is not None
    assert rule.when.any.kinds == ("task",)
    assert rule.when.any.terminal is True


def test_legacy_flat_flags_migrate_to_when() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "all_children_terminal": True,
            "any_children_terminal": True,
            "self": {"to": "DONE"},
        }
    ]
    when = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert when is not None
    assert when.all is not None and when.all.terminal is True
    assert when.any is not None and when.any.terminal is True


def test_legacy_min_terminal_is_rejected() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [{"min_children_terminal": 2, "self": {"to": "DONE"}}]
    with pytest.raises(PydanticValidationError, match="removed"):
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
        {"trigger": {"to": "IN_PROGRESS"}, "parent": {"to": "IN_PROGRESS"}},
        {"trigger": {"to": "DONE"}, "parent": {"to": "DONE"}, "on_error": "ignore"},
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
        {"trigger": {"to": "DONE"}, "parent": {"to": "DONE"}, "on_error": "warn"}
    ]
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(raw)


def _target_spec(self_body: dict) -> WorkflowSpec:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"any": {"terminal": True}},
            "self": self_body,
        }
    ]
    return WorkflowSpec.model_validate(raw)


def test_trigger_target_accepts_step_instead_of_to() -> None:
    resolved = _target_spec({"from": ["TO_TEST"], "step": "PASS"}).resolve("story")
    target = resolved.child_triggers[0].self_
    assert target.to is None
    assert target.step == "PASS"

    payload = serialize_definition(resolved, schema_version=4)
    stored = payload["child_triggers"][0]["self"]
    assert stored["step"] == "PASS"
    assert stored["to"] is None
    assert deserialize_definition("story", None, payload).child_triggers == resolved.child_triggers


def test_trigger_target_accepts_to_and_step_together() -> None:
    target = _target_spec({"to": "DONE", "step": "PASS"}).resolve("story").child_triggers[0].self_
    assert target.to == "DONE"
    assert target.step == "PASS"


def test_trigger_target_requires_to_or_step() -> None:
    with pytest.raises(PydanticValidationError, match="requires to or step"):
        _target_spec({"from": ["TO_TEST"]})


def test_trigger_target_step_must_be_a_key() -> None:
    with pytest.raises(PydanticValidationError, match="valid step key"):
        _target_spec({"step": "not a key"})


def test_trigger_from_to_support_start_and_terminal_predicates() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "trigger": {
                "kinds": ["task", "issue"],
                "from": {"terminal": False},
                "to": {"terminal": True},
            },
            "self": {"to": "DONE"},
        }
    ]
    trigger = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].trigger
    assert trigger is not None
    assert trigger.matches(
        "issue",
        None,
        "FIXING",
        "CLOSED_DONE",
        from_flags=_flags(),
        to_flags=_flags(terminal=True, main_terminal=True),
    )
    assert not trigger.matches(
        "task",
        "frontend",
        "DONE",
        "CANCELLED",
        from_flags=_flags(terminal=True, main_terminal=True),
        to_flags=_flags(terminal=True, main_terminal=True),
    )


def test_trigger_shorthand_string_and_list_normalize_to_statuses() -> None:
    trigger = _spec().resolve("task").parent_triggers[0].trigger
    assert trigger is not None
    assert trigger.from_.statuses == ("TODO",)
    assert trigger.to.statuses == ("IN_PROGRESS",)


def test_terminal_classification_defaults_to_all_main() -> None:
    resolved = _spec().resolve("task")
    assert resolved.main_terminal == resolved.terminal
    assert resolved.side_terminal == ()


def test_terminal_classification_explicit_side() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["side_terminal"] = ["CANCELLED"]
    resolved = WorkflowSpec.model_validate(raw).resolve("task")
    assert "CANCELLED" not in resolved.main_terminal
    assert resolved.side_terminal == ("CANCELLED",)


def test_terminal_classification_rejects_overlap() -> None:
    raw = _raw()
    raw["workflow_defs"]["task_standard"]["main_terminal"] = ["DONE", "CANCELLED"]
    raw["workflow_defs"]["task_standard"]["side_terminal"] = ["CANCELLED"]
    with pytest.raises(PydanticValidationError, match="disjoint"):
        WorkflowSpec.model_validate(raw)


def test_main_and_side_terminal_predicates() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "trigger": {
                "kinds": ["task"],
                "to": {"main_terminal": True},
            },
            "self": {"to": "DONE"},
        }
    ]
    trigger = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].trigger
    assert trigger is not None
    assert trigger.matches(
        "task",
        None,
        "IN_PROGRESS",
        "DONE",
        from_flags=_flags(),
        to_flags=_flags(terminal=True, main_terminal=True),
    )
    assert not trigger.matches(
        "task",
        None,
        "TODO",
        "CANCELLED",
        from_flags=_flags(start=True),
        to_flags=_flags(terminal=True, side_terminal=True),
    )


def test_when_and_cascades_predicates() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {
                "any": {
                    "kinds": ["task"],
                    "statuses": ["DONE"],
                    "and": {
                        "terminal": True,
                        "and": {"main_terminal": True},
                    },
                }
            },
            "self": {"to": "DONE"},
        }
    ]
    clause = WorkflowSpec.model_validate(raw).resolve("story").child_triggers[0].when
    assert clause is not None and clause.any is not None
    assert clause.any.matches_chain(
        "task", "frontend", "DONE", _flags(terminal=True, main_terminal=True)
    )
    assert not clause.any.matches_chain(
        "task", "frontend", "CANCELLED", _flags(terminal=True, side_terminal=True)
    )


def test_when_and_validation_is_recursive() -> None:
    raw = _raw()
    raw["kinds"]["story"]["child_triggers"] = [
        {
            "when": {"any": {"and": {"kinds": ["mystery"]}}},
            "self": {"to": "DONE"},
        }
    ]
    with pytest.raises(PydanticValidationError, match=r"any\.and: unknown child kinds"):
        WorkflowSpec.model_validate(raw)
