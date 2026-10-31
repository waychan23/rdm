"""Unit tests: canonical effective-definition serialization and pinned engines."""

from dataclasses import replace

import pyjson5
import pytest

from rdm.domain.errors import WorkflowGateBlocked
from rdm.domain.workflow.engine import GateChild, GateContext, WorkflowEngine
from rdm.domain.workflow.loader import load_spec
from rdm.domain.workflow.schema import WorkflowSpec
from rdm.domain.workflow.versioning import (
    canonical_json,
    definition_hash,
    definitions_equal,
    deserialize_definition,
    iter_effective_definitions,
    normalized_subtype,
    serialize_definition,
    validate_definition,
)


def _graph_spec(*, terminal: list[str] | None = None) -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {
            "version": 3,
            "kinds": {
                "task": {
                    "states": ["TODO", "DONE"],
                    "initial": "TODO",
                    "terminal": terminal or ["DONE"],
                    "steps": {
                        "TODO": [
                            {
                                "key": "FINISH",
                                "name": "完成",
                                "to": "DONE",
                                "gates": {"children_all_terminal": True},
                            }
                        ],
                        "DONE": [],
                    },
                }
            },
        }
    )


def test_canonical_json_ignores_object_order_and_comments() -> None:
    plain = pyjson5.loads('{"b": [2, 3], "a": 1}')
    commented = pyjson5.loads("{ /* comment */ a: 1, // line\n b: [2, 3] }")
    assert canonical_json(plain) == canonical_json(commented)
    assert definition_hash(plain) == definition_hash(commented)


def test_canonical_json_preserves_array_order() -> None:
    first = {"states": ["TODO", "DONE"]}
    second = {"states": ["DONE", "TODO"]}
    assert not definitions_equal(first, second)
    assert canonical_json(first) != canonical_json(second)


def test_round_trip_every_packaged_definition() -> None:
    spec = load_spec()
    seen = 0
    for kind, subtype, payload in iter_effective_definitions(spec):
        resolved = deserialize_definition(kind, subtype, payload)
        assert serialize_definition(resolved) == payload
        seen += 1
    assert seen > len(spec.kinds)


def test_iter_effective_definitions_covers_kinds_and_task_subtypes() -> None:
    spec = load_spec()
    keys = {(kind, subtype) for kind, subtype, _ in iter_effective_definitions(spec)}
    assert ("task", None) in keys
    for subtype in spec.kinds["task"].subtypes:
        assert ("task", subtype) in keys
    assert ("story", None) in keys


def test_schema_strategy_registry_rejects_unknown_version() -> None:
    from rdm.domain.workflow.schema_versions import (
        UnsupportedWorkflowSchema,
        get_schema_strategy,
    )

    assert get_schema_strategy(3).schema_version == 3
    with pytest.raises(UnsupportedWorkflowSchema):
        get_schema_strategy(999)


def test_new_schema_strategy_self_registers() -> None:
    from rdm.domain.workflow import schema_versions
    from rdm.domain.workflow.schema_versions import base, v3

    class SchemaTest(v3.SchemaV3):
        schema_version = 12345

    try:
        strategy = schema_versions.get_schema_strategy(12345)
        assert strategy.schema_version == 12345
        payload = strategy.serialize(load_spec().resolve("task"))
        resolved = strategy.deserialize("task", None, payload)
        assert resolved.kind == "task"
    finally:
        base._REGISTRY.pop(12345, None)


def test_normalized_subtype_is_task_only() -> None:
    assert normalized_subtype("task", "code_review") == "code_review"
    assert normalized_subtype("task", "") is None
    assert normalized_subtype("task", None) is None
    assert normalized_subtype("story", "ignored") is None


def _definition_with_edge() -> tuple[str, str | None, dict]:
    for kind, subtype, payload in iter_effective_definitions(load_spec()):
        if any(payload["steps"][state] for state in payload["states"]):
            return kind, subtype, payload
    raise AssertionError("packaged workflow has no edges")


def test_deserialize_rejects_unknown_step_target() -> None:
    kind, subtype, payload = _definition_with_edge()
    mutated = pyjson5.loads(canonical_json(payload))
    state = next(state for state in mutated["states"] if mutated["steps"][state])
    mutated["steps"][state][0]["to"] = "GONE"
    with pytest.raises(ValueError, match="targets unknown state"):
        deserialize_definition(kind, subtype, mutated)


def test_deserialize_rejects_missing_state_steps() -> None:
    spec = load_spec()
    kind, subtype, payload = next(iter_effective_definitions(spec))
    mutated = pyjson5.loads(canonical_json(payload))
    removed = mutated["states"][0]
    mutated["steps"].pop(removed)
    with pytest.raises(ValueError, match="steps must be declared for every state"):
        deserialize_definition(kind, subtype, mutated)


def test_deserialize_rejects_kind_mismatch() -> None:
    kind, _, payload = next(iter_effective_definitions(load_spec()))
    wrong_kind = "story" if kind != "story" else "epic"
    with pytest.raises(ValueError, match="kind mismatch"):
        deserialize_definition(wrong_kind, None, payload)


def test_validate_definition_rejects_initial_outside_states() -> None:
    spec = _graph_spec()
    resolved = deserialize_definition("task", None, serialize_definition(spec.resolve("task")))
    broken = type(resolved)(
        kind=resolved.kind,
        task_type=resolved.task_type,
        label=resolved.label,
        label_en=resolved.label_en,
        states=resolved.states,
        initial="GONE",
        terminal=resolved.terminal,
        steps=resolved.steps,
        gates=resolved.gates,
        fields=resolved.fields,
    )
    with pytest.raises(ValueError, match="initial state not in states"):
        validate_definition(broken)


def test_pinned_engine_resolves_pinned_definition() -> None:
    current = _graph_spec()
    pinned_def = replace(current.resolve("task"), terminal=("DONE", "CANCELLED"))
    engine = WorkflowEngine(current, pinned={("task", "legacy"): pinned_def})

    assert engine.resolve("task", "legacy").terminal == ("DONE", "CANCELLED")
    assert engine.resolve("task", "other").terminal == ("DONE",)
    assert engine.is_terminal("task", "CANCELLED", task_type="legacy") is True
    assert engine.is_terminal("task", "CANCELLED", task_type="other") is False


def test_gate_child_terminal_override() -> None:
    engine = WorkflowEngine(_graph_spec())
    blocked = GateContext(
        children=[GateChild(kind="task", status="DONE", display_id="T-1", terminal=False)]
    )
    with pytest.raises(WorkflowGateBlocked):
        engine.check("task", "TODO", "DONE", context=blocked, step_key="FINISH")

    passed = GateContext(
        children=[GateChild(kind="task", status="TODO", display_id="T-1", terminal=True)]
    )
    engine.check("task", "TODO", "DONE", context=passed, step_key="FINISH")
