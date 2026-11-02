"""Dedicated workflow definition for behavior tests.

Behavior tests must not depend on the packaged ``src/rdm/resources/workflow-configs/default.json5``:
product edits to the shipped state machine should not cause a wave of unrelated
test failures. ``tests/resources/workflow.json5`` is the stable test contract
(see its header comment).

Tests that assert the *packaged* definition itself (supply, refs, CLI doctor,
contract workflow-version tests) keep using
``rdm.domain.workflow.loader.load_spec/load_engine``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pyjson5

from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec

SPEC_PATH = Path(__file__).with_name("resources") / "workflow.json5"

# Modules that bind ``load_engine``/``load_spec`` at import time. Module-level
# ``from ... import`` means patching the loader alone is not enough.
_ENGINE_TARGETS = (
    "rdm.domain.workflow.loader",
    "rdm.application.services.overview_service",
    "rdm.application.services.sprint_service",
    "rdm.application.services.step_service",
    "rdm.application.services.todo_service",
    "rdm.application.services.workflow_version_service",
    "rdm.application.services.workitem_service",
    "rdm.interfaces.http.workitem",
)
_SPEC_TARGETS = ("rdm.application.services.workflow_service",)


def load_test_spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_test_spec() -> WorkflowSpec:
    return WorkflowSpec.model_validate(pyjson5.loads(load_test_spec_text()))


@lru_cache(maxsize=1)
def load_test_engine() -> WorkflowEngine:
    return WorkflowEngine(load_test_spec())


def install_test_engine(monkeypatch: Any) -> WorkflowEngine:
    """Point every service/HTTP/MCP path at the test definition."""
    engine = load_test_engine()
    spec = load_test_spec()
    for target in _ENGINE_TARGETS:
        monkeypatch.setattr(f"{target}.load_engine", lambda: engine)
    for target in _SPEC_TARGETS:
        monkeypatch.setattr(f"{target}.load_spec", lambda: spec)
    return engine
