"""Unit tests: workflow JSON5 loading, freezing and schema validation."""

import pyjson5
import pytest
from pydantic import ValidationError as PydanticValidationError

from rdm.domain.workflow.loader import load_engine, load_spec, load_spec_text
from rdm.domain.workflow.schema import WorkflowSpec


def test_json5_loads_and_engine_is_singleton() -> None:
    spec1 = load_spec()
    spec2 = load_spec()
    assert spec1 is spec2
    assert load_engine() is load_engine()
    raw = pyjson5.loads(load_spec_text())
    assert raw["version"] == 3
    assert "kinds" in raw and "task_types" in raw


def test_spec_is_frozen() -> None:
    spec = load_spec()
    with pytest.raises(PydanticValidationError):
        spec.version = 2  # type: ignore[misc]


def test_bad_spec_rejected_unknown_transition_target() -> None:
    bad = {
        "version": 1,
        "kinds": {
            "x": {
                "states": ["A", "B"],
                "initial": "A",
                "terminal": ["B"],
                "transitions": {"A": ["ZZZ"], "B": []},
                "gates": {},
            }
        },
    }
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(bad)


def test_bad_spec_rejected_missing_transition_entry() -> None:
    bad = {
        "version": 1,
        "kinds": {
            "x": {
                "states": ["A", "B"],
                "initial": "A",
                "terminal": ["B"],
                "transitions": {"A": ["B"]},  # B missing
            }
        },
    }
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(bad)


def test_gate_requires_a_condition() -> None:
    bad = {
        "version": 1,
        "kinds": {
            "x": {
                "states": ["A", "B"],
                "initial": "A",
                "terminal": ["B"],
                "transitions": {"A": ["B"], "B": []},
                "gates": {"B": {}},
            }
        },
    }
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(bad)


def test_extra_gate_field_forbidden() -> None:
    bad = {
        "version": 1,
        "kinds": {
            "x": {
                "states": ["A", "B"],
                "initial": "A",
                "terminal": ["B"],
                "transitions": {"A": ["B"], "B": []},
                "gates": {"B": {"children_all_terminal": True, "mystery": 1}},
            }
        },
    }
    with pytest.raises(PydanticValidationError):
        WorkflowSpec.model_validate(bad)
