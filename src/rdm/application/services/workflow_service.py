"""Single producer of the workflow definition DTO shared by REST and MCP.

mcp-tools.md §7 / architecture §14: workflow_get output must be byte-identical
to GET /api/v1/workflow — both call build_workflow_dto() (S10 parity test).
"""

from __future__ import annotations

from typing import Any

from rdm.domain.workflow.loader import load_spec
from rdm.domain.workflow.schema import WorkflowSpec


def build_workflow_dto(spec: WorkflowSpec | None = None, kind: str | None = None) -> dict[str, Any]:
    spec = spec or load_spec()
    if kind is not None and not spec.has_kind(kind):
        from rdm.domain.errors import ValidationError

        raise ValidationError(
            f"未知 kind {kind!r}",
            details={"kind": kind, "allowed": sorted(spec.kinds)},
        )
    names = [kind] if kind else list(spec.kinds)
    return {
        "version": spec.version,
        "kinds": {
            name: {
                "states": list(spec.kinds[name].states),
                "initial": spec.kinds[name].initial,
                "terminal": list(spec.kinds[name].terminal),
                "transitions": {
                    src: list(targets) for src, targets in spec.kinds[name].transitions.items()
                },
                "gates": {
                    target: gate.model_dump(exclude_none=True)
                    for target, gate in spec.kinds[name].gates.items()
                },
            }
            for name in names
        },
    }
