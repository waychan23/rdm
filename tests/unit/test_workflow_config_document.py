"""Unit: workflow config document envelope and schema-version gates (RDM-84)."""

from __future__ import annotations

import json

import pyjson5
import pytest

from rdm.domain.workflow.config import (
    WorkflowConfigDocumentError,
    parse_config_document,
)
from rdm.domain.workflow.loader import load_spec_text


def _raw(**changes: object) -> dict:
    raw = pyjson5.loads(load_spec_text())
    raw.update(changes)
    return raw


def test_packaged_default_has_key_and_name() -> None:
    document = parse_config_document(load_spec_text())
    assert document.key == "default"
    assert document.name == "默认工作流"
    assert document.schema_version == 4
    assert document.text


def test_missing_key_and_name_are_rejected() -> None:
    raw = _raw()
    raw.pop("key")
    raw.pop("name")
    with pytest.raises(WorkflowConfigDocumentError):
        parse_config_document(json.dumps(raw))


@pytest.mark.parametrize("key", ["Default", "x", "has space", "-leading", ""])
def test_invalid_config_key_rejected(key: str) -> None:
    with pytest.raises(WorkflowConfigDocumentError):
        parse_config_document(json.dumps(_raw(key=key, name="x")))


def test_stale_schema_version_is_rejected() -> None:
    raw = _raw(key="old", name="Old", version=3)
    with pytest.raises(WorkflowConfigDocumentError, match="最新版本"):
        parse_config_document(json.dumps(raw))


def test_malformed_json5_is_wrapped() -> None:
    with pytest.raises(WorkflowConfigDocumentError):
        parse_config_document("{ this is not json5")
