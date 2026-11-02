"""workflow.json5 schema version 3 (named steps, executor ranges, gates)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rdm.domain.workflow.schema import (
    FieldsSpec,
    GateSpec,
    ResolvedKindWorkflow,
    StepSpec,
)
from rdm.domain.workflow.schema_versions.base import DefinitionSchema, normalized_subtype


class SchemaV3(DefinitionSchema):
    """Current schema (workflow.json5 ``version: 3``).

    The full field set is kept on purpose: ``ExecutorRange.max=None`` means
    "unbounded" while its default is 1, so ``exclude_none`` would change it.
    """

    schema_version = 3

    def _serialize(self, resolved: ResolvedKindWorkflow) -> dict[str, Any]:
        return {
            "kind": resolved.kind,
            "subtype": resolved.task_type,
            "label": resolved.label,
            "label_en": resolved.label_en,
            "states": list(resolved.states),
            "initial": resolved.initial,
            "terminal": list(resolved.terminal),
            "steps": {
                state: [step.model_dump(mode="json") for step in steps]
                for state, steps in resolved.steps.items()
            },
            "gates": {
                target: gate.model_dump(mode="json") for target, gate in resolved.gates.items()
            },
            "fields": resolved.fields.model_dump(mode="json"),
        }

    def _deserialize(
        self,
        kind: str,
        subtype: str | None,
        payload: Mapping[str, Any],
    ) -> ResolvedKindWorkflow:
        return ResolvedKindWorkflow(
            kind=kind,
            task_type=normalized_subtype(kind, subtype),
            label=str(payload["label"]),
            label_en=payload.get("label_en"),
            states=tuple(payload["states"]),
            initial=str(payload["initial"]),
            terminal=tuple(payload["terminal"]),
            # Historical schema has no classification: treat every terminal
            # state as a normal (main) terminal (§17.148).
            main_terminal=tuple(payload["terminal"]),
            steps={
                state: tuple(StepSpec.model_validate(step) for step in steps)
                for state, steps in payload["steps"].items()
            },
            gates={
                target: GateSpec.model_validate(gate)
                for target, gate in payload.get("gates", {}).items()
            },
            fields=FieldsSpec.model_validate(payload["fields"]),
        )
