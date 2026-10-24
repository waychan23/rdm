"""Unit tests for project key validation and event payloads."""

import pytest

from rdm.application.dto import validate_project_key
from rdm.domain.errors import ValidationError
from rdm.domain.events import EventType, status_changed_payload


@pytest.mark.parametrize("key", ["RDM", "DEMO", "AB12", "A1"])
def test_project_key_valid(key: str) -> None:
    assert validate_project_key(key) == key


@pytest.mark.parametrize("key", ["", "A", "TOOLONGKEY123", "demo", "DEMO_1", "中文", "AB-C"])
def test_project_key_invalid(key: str) -> None:
    with pytest.raises(ValidationError):
        validate_project_key(key)


def test_status_changed_payload_shape() -> None:
    payload = status_changed_payload("TODO", "IN_PROGRESS", ["TO_REVIEW", "CANCELLED"])
    assert payload == {
        "changes": {"status": ["TODO", "IN_PROGRESS"]},
        "allowed_next": ["TO_REVIEW", "CANCELLED"],
        "gate": None,
    }
    assert EventType.WORK_ITEM_STATUS_CHANGED == "work_item.status_changed"
