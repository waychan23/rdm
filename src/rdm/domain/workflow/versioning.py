"""Canonical serialization of effective workflow definitions (§17.120).

An effective definition is the post-expansion ``ResolvedKindWorkflow`` for one
``(kind, subtype)`` pair. It is persisted verbatim so work items keep running on
the definition they were created under, independent of later config changes.

The payload shape is owned by a schema-version strategy
(:mod:`rdm.domain.workflow.schema_versions`); this module only provides the
canonical comparison/hash layer shared by every schema version.

Equality is based on canonical JSON: object keys are sorted (object order is
not behavioural), arrays keep their order (states/steps order is observable),
and JSON5 comments have already disappeared at parse time.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from rdm.domain.workflow.schema import ResolvedKindWorkflow, WorkflowSpec
from rdm.domain.workflow.schema_versions import (
    DefinitionSchema,
    UnsupportedWorkflowSchema,
    get_schema_strategy,
    latest_schema_version,
    normalized_subtype,
    validate_definition,
)

__all__ = [
    "DefinitionSchema",
    "UnsupportedWorkflowSchema",
    "canonical_json",
    "definition_hash",
    "definitions_equal",
    "deserialize_definition",
    "get_schema_strategy",
    "iter_effective_definitions",
    "latest_schema_version",
    "normalized_subtype",
    "serialize_definition",
    "validate_definition",
]


def canonical_json(value: Any) -> str:
    """Stable JSON: recursively sorted object keys, preserved array order."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def definition_hash(definition: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()


def definitions_equal(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Compare canonical strings, not hashes, to rule out collisions."""
    return canonical_json(a) == canonical_json(b)


def serialize_definition(
    resolved: ResolvedKindWorkflow,
    *,
    schema_version: int | None = None,
) -> dict[str, Any]:
    """Serialize with ``schema_version`` (defaults to the newest strategy)."""
    version = schema_version if schema_version is not None else latest_schema_version()
    return get_schema_strategy(version).serialize(resolved)


def deserialize_definition(
    kind: str,
    subtype: str | None,
    payload: Mapping[str, Any],
    *,
    schema_version: int | None = None,
) -> ResolvedKindWorkflow:
    """Deserialize using the stored schema version (``format`` by default)."""
    version = schema_version if schema_version is not None else payload.get("format")
    if not isinstance(version, int):
        raise UnsupportedWorkflowSchema(
            f"workflow definition has no valid schema version: {version!r}"
        )
    return get_schema_strategy(version).deserialize(kind, subtype, payload)


def iter_effective_definitions(
    spec: WorkflowSpec,
) -> Iterable[tuple[str, str | None, dict[str, Any]]]:
    """Yield ``(kind, subtype, payload)`` for every definition the spec exposes."""
    for kind in spec.kinds:
        yield kind, None, serialize_definition(spec.resolve(kind), schema_version=spec.version)
        if kind != "task":
            continue
        for subtype in spec.kinds[kind].subtypes:
            yield (
                kind,
                subtype,
                serialize_definition(spec.resolve(kind, subtype), schema_version=spec.version),
            )
