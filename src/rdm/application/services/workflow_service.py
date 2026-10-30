"""Single producer of the workflow definition DTO shared by REST and MCP.

mcp-tools.md §7 / architecture §14: workflow_get output must be byte-identical
to GET /api/v1/workflow — both call build_workflow_dto() (S10 parity test).
"""

from __future__ import annotations

from typing import Any

from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_spec
from rdm.domain.workflow.schema import (
    FieldsSpec,
    GateSpec,
    ResolvedKindWorkflow,
    StepSpec,
    WorkflowSpec,
)


def _gate_dto(gate: GateSpec | None) -> dict[str, Any]:
    if gate is None:
        return {}
    return gate.model_dump(exclude_none=True)


def _fields_dto(fields: FieldsSpec) -> dict[str, Any]:
    return {
        "reviewer": fields.reviewer,
        "review_content": fields.review_content,
        "custom": [
            {
                "key": field.key,
                "label": field.label,
                "type": field.type,
                "multiple": field.multiple,
            }
            for field in fields.custom
        ],
    }


def _step_dto(engine: WorkflowEngine, kind: str, src: str, step: StepSpec) -> dict[str, Any]:
    gate = engine.effective_gate(kind, src, step)
    return {
        "key": step.key,
        "name": step.name,
        "to": step.to,
        "mode": step.mode,
        "actors": list(step.actors),
        "executors": step.executors.model_dump(),
        "note": step.note,
        "gates": _gate_dto(gate),
        "tasks": step.tasks.model_dump() if step.tasks is not None else None,
    }


def _workflow_dto(
    engine: WorkflowEngine,
    resolved: ResolvedKindWorkflow,
    *,
    include_subtypes: bool,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "label": resolved.label,
        "states": list(resolved.states),
        "initial": resolved.initial,
        "terminal": list(resolved.terminal),
        "transitions": {src: list(resolved.allowed(src)) for src in resolved.states},
        "steps": {
            src: [_step_dto(engine, resolved.kind, src, step) for step in resolved.steps_from(src)]
            for src in resolved.states
        },
        "gates": {target: _gate_dto(gate) for target, gate in resolved.gates.items()},
        "fields": _fields_dto(resolved.fields),
    }
    if include_subtypes:
        base = engine.spec.kinds[resolved.kind]
        data["subtypes"] = {
            task_type: {
                **_workflow_dto(
                    engine,
                    engine.resolve(resolved.kind, task_type),
                    include_subtypes=False,
                ),
                "inherits": resolved.kind,
            }
            for task_type in base.subtypes
        }
    return data


def build_workflow_dto(
    spec: WorkflowSpec | None = None,
    kind: str | None = None,
    task_type: str | None = None,
) -> dict[str, Any]:
    spec = spec or load_spec()
    if kind is not None and not spec.has_kind(kind):
        from rdm.domain.errors import ValidationError

        raise ValidationError(
            f"未知 kind {kind!r}",
            details={"kind": kind, "allowed": sorted(spec.kinds)},
        )
    if task_type is not None and task_type not in spec.task_types:
        from rdm.domain.errors import ValidationError

        raise ValidationError(
            f"未知 task_type {task_type!r}",
            details={"task_type": task_type, "allowed": sorted(spec.task_types)},
        )
    engine = WorkflowEngine(spec)
    names = [kind] if kind else list(spec.kinds)
    kinds: dict[str, Any] = {}
    for name in names:
        if task_type is not None:
            resolved = engine.resolve(name, task_type)
            kinds[name] = _workflow_dto(engine, resolved, include_subtypes=False)
        else:
            resolved = engine.resolve(name)
            kinds[name] = _workflow_dto(engine, resolved, include_subtypes=True)
    return {
        "version": spec.version,
        "revision": spec.revision,
        "task_types": [{"value": code, "label": label} for code, label in spec.task_types.items()],
        "kinds": kinds,
    }
