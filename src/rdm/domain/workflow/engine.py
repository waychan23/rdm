"""Workflow engine: named step lookup + gate evaluation.

Validation order (architecture §5.2):
state exists -> step/edge in table -> target gate conditions.
Permission checks happen later in the service layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rdm.domain.errors import ValidationError, WorkflowGateBlocked, WorkflowIllegalTransition
from rdm.domain.workflow.schema import (
    GateSpec,
    ResolvedKindWorkflow,
    StepSpec,
    WorkflowSpec,
    merge_gates,
)


@dataclass(frozen=True)
class GateChild:
    """A direct child item relevant to children_all_terminal / min_children."""

    kind: str
    status: str
    display_id: str


@dataclass(frozen=True)
class GateSprintItem:
    """A sprint member item relevant to no_nonterminal_sprint_items."""

    kind: str
    status: str
    display_id: str


@dataclass(frozen=True)
class GateContext:
    children: Sequence[GateChild] = ()
    sprint_items: Sequence[GateSprintItem] = ()
    # Flattened field values for required_fields: master fields, kind-specific
    # fields, reviewer ids, review_content_md and custom fields.
    field_values: Mapping[str, Any] = field(default_factory=dict)
    field_labels: Mapping[str, str] = field(default_factory=dict)


def _field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


class WorkflowEngine:
    def __init__(self, spec: WorkflowSpec) -> None:
        self._spec = spec
        self._resolved: dict[tuple[str, str | None], ResolvedKindWorkflow] = {}

    @property
    def spec(self) -> WorkflowSpec:
        return self._spec

    # --- resolution -------------------------------------------------------

    def resolve(self, kind: str, task_type: str | None = None) -> ResolvedKindWorkflow:
        key = (kind, task_type if kind == "task" else None)
        resolved = self._resolved.get(key)
        if resolved is not None:
            return resolved
        if not self._spec.has_kind(kind):
            raise ValidationError(
                f"未知工作项类型 {kind!r}",
                details={"kind": kind, "allowed": sorted(self._spec.kinds)},
            )
        try:
            resolved = self._spec.resolve(kind, key[1])
        except ValueError as exc:
            raise ValidationError(
                f"工作流定义无效：{exc}",
                details={"kind": kind, "task_type": key[1]},
            ) from exc
        self._resolved[key] = resolved
        return resolved

    def _resolved_or_error(self, kind: str, task_type: str | None) -> ResolvedKindWorkflow:
        resolved = self.resolve(kind, task_type)
        if task_type is not None and kind == "task":
            # An unknown task type falls back to the base workflow. Services
            # validate membership against task_types before calling us.
            pass
        return resolved

    def initial_status(self, kind: str, task_type: str | None = None) -> str:
        return self.resolve(kind, task_type).initial

    def is_terminal(self, kind: str, status: str, task_type: str | None = None) -> bool:
        return status in self.resolve(kind, task_type).terminal

    def terminal_states(self, kind: str, task_type: str | None = None) -> tuple[str, ...]:
        return tuple(self.resolve(kind, task_type).terminal)

    def all_terminal_states(self) -> tuple[str, ...]:
        states: set[str] = set()
        for kind, kw in self._spec.kinds.items():
            states.update(self.resolve(kind).terminal)
            for task_type in kw.subtypes:
                states.update(self.resolve(kind, task_type).terminal)
        return tuple(sorted(states))

    # --- step lookup ------------------------------------------------------

    def steps_from(
        self, kind: str, status: str, task_type: str | None = None
    ) -> tuple[StepSpec, ...]:
        resolved = self.resolve(kind, task_type)
        if status not in resolved.states:
            raise ValidationError(
                f"状态 {status!r} 不属于 kind={kind}",
                details={"kind": kind, "status": status, "allowed": list(resolved.states)},
            )
        return resolved.steps_from(status)

    def allowed(self, kind: str, status: str, task_type: str | None = None) -> tuple[str, ...]:
        resolved = self.resolve(kind, task_type)
        if status not in resolved.states:
            raise ValidationError(
                f"状态 {status!r} 不属于 kind={kind}",
                details={"kind": kind, "status": status, "allowed": list(resolved.states)},
            )
        return resolved.allowed(status)

    def resolve_step(
        self,
        kind: str,
        src: str,
        *,
        dst: str | None = None,
        key: str | None = None,
        task_type: str | None = None,
        item: str | None = None,
    ) -> StepSpec:
        resolved = self.resolve(kind, task_type)
        if src not in resolved.states:
            raise ValidationError(
                f"当前状态 {src!r} 不属于 kind={kind}",
                details={"kind": kind, "status": src, "allowed": list(resolved.states)},
            )
        if dst is not None and dst not in resolved.states:
            raise ValidationError(
                f"目标状态 {dst!r} 不属于 kind={kind}",
                details={"kind": kind, "status": dst, "allowed": list(resolved.states)},
            )
        steps = resolved.steps_from(src)
        label = f"{item} " if item else ""
        if key is not None:
            matches = [step for step in steps if step.key == key]
            if not matches:
                raise WorkflowIllegalTransition(
                    f"{label}当前状态 {src} 没有步骤 {key!r}",
                    details={
                        "kind": kind,
                        "from": src,
                        "step_key": key,
                        "available_steps": _steps_details(steps),
                        "allowed_transitions": list(resolved.allowed(src)),
                    },
                )
            step = matches[0]
            if dst is not None and step.to != dst:
                raise WorkflowIllegalTransition(
                    f"{label}步骤 {key!r} 的目标是 {step.to}，不是 {dst}",
                    details={
                        "kind": kind,
                        "from": src,
                        "step_key": key,
                        "to": step.to,
                        "target": dst,
                        "available_steps": _steps_details(steps),
                    },
                )
            return step

        matches = [step for step in steps if step.to == dst]
        if not matches:
            raise WorkflowIllegalTransition(
                f"{label}不能从 {src} 转到 {dst}。允许：{list(resolved.allowed(src))}。",
                details={
                    "kind": kind,
                    "from": src,
                    "to": dst,
                    "allowed_transitions": list(resolved.allowed(src)),
                    "available_steps": _steps_details(steps),
                },
            )
        if len(matches) > 1:
            raise WorkflowIllegalTransition(
                f"{label}从 {src} 到 {dst} 有多个步骤，必须显式指定 step。",
                details={
                    "kind": kind,
                    "from": src,
                    "to": dst,
                    "available_steps": _steps_details(matches),
                    "hint": "使用 steps 中的 key 指定具体步骤。",
                },
            )
        return matches[0]

    def effective_gate(
        self,
        kind: str,
        src: str,
        step: StepSpec,
        task_type: str | None = None,
    ) -> GateSpec | None:
        resolved = self.resolve(kind, task_type)
        gate = merge_gates(resolved.gates.get(step.to), step.gates)
        if gate is not None and gate.is_empty():
            return None
        return gate

    # --- validation -------------------------------------------------------

    def check(
        self,
        kind: str,
        src: str,
        dst: str,
        *,
        item: str | None = None,
        context: GateContext | None = None,
        step_key: str | None = None,
        task_type: str | None = None,
    ) -> None:
        """Raise on an illegal step or an unmet gate; return None if OK."""
        resolved = self.resolve(kind, task_type)
        if src not in resolved.states:
            raise ValidationError(
                f"当前状态 {src!r} 不属于 kind={kind}",
                details={"kind": kind, "status": src, "allowed": list(resolved.states)},
            )
        if dst not in resolved.states:
            raise ValidationError(
                f"目标状态 {dst!r} 不属于 kind={kind}",
                details={"kind": kind, "status": dst, "allowed": list(resolved.states)},
            )

        step = self.resolve_step(
            kind,
            src,
            dst=dst,
            key=step_key,
            task_type=task_type,
            item=item,
        )
        gate = self.effective_gate(kind, src, step, task_type=task_type)
        if gate is not None:
            self._check_gate(
                src,
                dst,
                gate,
                item,
                context or GateContext(),
                resolved.allowed(src),
                step=step,
            )

    def _check_gate(
        self,
        src: str,
        dst: str,
        gate: GateSpec,
        item: str | None,
        ctx: GateContext,
        allowed_next: tuple[str, ...],
        *,
        step: StepSpec,
    ) -> None:
        label = item or step.to
        blocking: list[str] = []
        extra: dict[str, object] = {}
        reasons: list[str] = []

        if gate.children_all_terminal:
            blocking_children = [
                c.display_id for c in ctx.children if not self.is_terminal(c.kind, c.status)
            ]
            if blocking_children:
                blocking.extend(blocking_children)
                reasons.append(f"{len(blocking_children)} 个子项未终态")

        if gate.min_children is not None and len(ctx.children) < gate.min_children:
            extra["min_children"] = gate.min_children
            extra["child_count"] = len(ctx.children)
            reasons.append(f"至少需要 {gate.min_children} 个子项，当前 {len(ctx.children)} 个")

        if gate.no_nonterminal_sprint_items:
            blocking_items = [
                i.display_id for i in ctx.sprint_items if not self.is_terminal(i.kind, i.status)
            ]
            if blocking_items:
                blocking.extend(blocking_items)
                reasons.append(f"{len(blocking_items)} 个 Sprint 内工作项未终态")

        if gate.required_fields:
            missing: list[dict[str, str]] = []
            for key in gate.required_fields:
                if not _field_present(ctx.field_values.get(key)):
                    missing.append({"key": key, "label": ctx.field_labels.get(key, key)})
            if missing:
                extra["missing_fields"] = missing
                labels = "、".join(item["label"] for item in missing)
                reasons.append(f"必填字段未填写：{labels}")

        if not reasons:
            return

        details = {
            "item": item,
            "from": src,
            "target": dst,
            "step_key": step.key,
            "step_name": step.name,
            "blocking_children": blocking,
            "allowed_transitions": list(allowed_next),
            "hint": "先完成阻塞项或补齐必填字段，再重试；必要时用 comment_add 通知负责人。",
            **extra,
        }
        raise WorkflowGateBlocked(
            f"{label} 不能执行步骤「{step.name}」进入 {dst}：{'；'.join(reasons)}",
            details=details,
        )


def _steps_details(steps: Sequence[StepSpec]) -> list[dict[str, Any]]:
    return [
        {
            "key": step.key,
            "name": step.name,
            "to": step.to,
            "mode": step.mode,
            "note": step.note,
        }
        for step in steps
    ]
