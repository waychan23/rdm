"""workflow.json5 schema version 4 (parent triggers, §17.137).

Version 4 is version 3 plus the optional ``parent_triggers`` list. The list is
always serialized (possibly empty) so the canonical definition tells apart "no
rules" from historical schema-3 records, which never had the field.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rdm.domain.workflow.schema import (
    FieldsSpec,
    GateSpec,
    ParentTriggerSpec,
    ResolvedKindWorkflow,
    StepSpec,
)
from rdm.domain.workflow.schema_versions.base import DefinitionSchema, normalized_subtype


class SchemaV4(DefinitionSchema):
    """Current schema (workflow.json5 ``version: 4``)."""

    schema_version = 4

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
            "parent_triggers": [
                trigger.model_dump(mode="json", by_alias=True)
                for trigger in resolved.parent_triggers
            ],
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
            steps={
                state: tuple(StepSpec.model_validate(step) for step in steps)
                for state, steps in payload["steps"].items()
            },
            gates={
                target: GateSpec.model_validate(gate)
                for target, gate in payload.get("gates", {}).items()
            },
            fields=FieldsSpec.model_validate(payload["fields"]),
            parent_triggers=tuple(
                ParentTriggerSpec.model_validate(trigger)
                for trigger in payload.get("parent_triggers", [])
            ),
        )
