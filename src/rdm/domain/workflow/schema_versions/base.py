"""Shared template/registry for persisted workflow-definition schemas (§17.120).

Each concrete version lives in its own module (``v3.py``, ``v4.py``, ...). The
template method in :class:`DefinitionSchema` owns the common envelope checks and
structural validation; a version module only implements how that version turns a
resolved definition into JSON and back.

Version modules register themselves via ``__init_subclass__``; the package
``__init__`` imports them. Adding a version therefore means adding one module
and one import — the registry and all callers stay untouched (OCP).
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from rdm.domain.workflow.schema import ResolvedKindWorkflow


class UnsupportedWorkflowSchema(ValueError):
    """The server does not (or no longer) implement this config schema."""


def normalized_subtype(kind: str, subtype: str | None) -> str | None:
    """Subtypes only exist for ``task``; empty/blank means no subtype."""
    if kind != "task":
        return None
    value = (subtype or "").strip()
    return value or None


def validate_definition(resolved: ResolvedKindWorkflow) -> None:
    """Structural invariants that do not depend on the current spec."""
    states = list(resolved.states)
    if not states:
        raise ValueError(f"{resolved.kind}/{resolved.task_type}: states must not be empty")
    if len(set(states)) != len(states):
        raise ValueError(f"{resolved.kind}/{resolved.task_type}: duplicate states")
    if resolved.initial not in states:
        raise ValueError(f"{resolved.kind}/{resolved.task_type}: initial state not in states")
    if not set(resolved.terminal) <= set(states):
        raise ValueError(f"{resolved.kind}/{resolved.task_type}: terminal state not in states")
    if set(resolved.steps) != set(states):
        raise ValueError(
            f"{resolved.kind}/{resolved.task_type}: steps must be declared for every state"
        )
    for state, steps in resolved.steps.items():
        keys = [step.key for step in steps]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{resolved.kind}/{resolved.task_type}/{state}: duplicate step keys")
        for step in steps:
            if step.to not in states:
                raise ValueError(
                    f"{resolved.kind}/{resolved.task_type}/{state}: "
                    f"step {step.key!r} targets unknown state {step.to!r}"
                )
    for target in resolved.gates:
        if target not in states:
            raise ValueError(
                f"{resolved.kind}/{resolved.task_type}: gate targets unknown state {target!r}"
            )


class DefinitionSchema(ABC):
    """Template for one persisted-definition schema version."""

    schema_version: ClassVar[int]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        version = getattr(cls, "schema_version", None)
        if version is None or inspect.isabstract(cls):
            return
        if not isinstance(version, int) or version < 1:
            raise ValueError(f"invalid workflow schema version: {version!r}")
        if version in _REGISTRY:
            raise ValueError(f"duplicate workflow schema strategy for version {version}")
        _REGISTRY[version] = cls()

    # --- template methods -------------------------------------------------

    def serialize(self, resolved: ResolvedKindWorkflow) -> dict[str, Any]:
        payload = self._serialize(resolved)
        payload["format"] = self.schema_version
        return payload

    def deserialize(
        self,
        kind: str,
        subtype: str | None,
        payload: Mapping[str, Any],
    ) -> ResolvedKindWorkflow:
        if payload.get("format") != self.schema_version:
            raise ValueError(
                f"workflow definition format mismatch: stored {payload.get('format')!r}, "
                f"expected {self.schema_version}"
            )
        if payload.get("kind") != kind:
            raise ValueError(
                "workflow definition kind mismatch: "
                f"stored {payload.get('kind')!r}, expected {kind!r}"
            )
        stored_subtype = payload.get("subtype")
        if normalized_subtype(kind, stored_subtype) != normalized_subtype(kind, subtype):
            raise ValueError(
                "workflow definition subtype mismatch: "
                f"stored {stored_subtype!r}, expected {subtype!r}"
            )
        resolved = self._deserialize(kind, subtype, payload)
        validate_definition(resolved)
        return resolved

    # --- per-version hooks ------------------------------------------------

    @abstractmethod
    def _serialize(self, resolved: ResolvedKindWorkflow) -> dict[str, Any]: ...

    @abstractmethod
    def _deserialize(
        self,
        kind: str,
        subtype: str | None,
        payload: Mapping[str, Any],
    ) -> ResolvedKindWorkflow: ...


_REGISTRY: dict[int, DefinitionSchema] = {}


def get_schema_strategy(schema_version: int) -> DefinitionSchema:
    strategy = _REGISTRY.get(schema_version)
    if strategy is None:
        raise UnsupportedWorkflowSchema(
            f"unsupported workflow config schema version {schema_version}; "
            f"available: {sorted(_REGISTRY)}"
        )
    return strategy


def latest_schema_version() -> int:
    if not _REGISTRY:
        raise UnsupportedWorkflowSchema("no workflow schema strategies registered")
    return max(_REGISTRY)
