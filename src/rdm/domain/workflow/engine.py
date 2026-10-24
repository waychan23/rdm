"""Workflow engine: transition table lookup + gate evaluation.

Validation order (architecture §5.2):
state exists -> transition in table -> target gate conditions.
Permission checks happen later in the service layer.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rdm.domain.errors import ValidationError, WorkflowGateBlocked, WorkflowIllegalTransition
from rdm.domain.workflow.schema import GateSpec, KindWorkflow, WorkflowSpec


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


class WorkflowEngine:
    def __init__(self, spec: WorkflowSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> WorkflowSpec:
        return self._spec

    def _kind(self, kind: str) -> KindWorkflow:
        if not self._spec.has_kind(kind):
            raise ValidationError(
                f"未知工作项类型 {kind!r}",
                details={"kind": kind, "allowed": sorted(self._spec.kinds)},
            )
        return self._spec.kind(kind)

    def initial_status(self, kind: str) -> str:
        return self._kind(kind).initial

    def is_terminal(self, kind: str, status: str) -> bool:
        return status in self._kind(kind).terminal

    def allowed(self, kind: str, status: str) -> tuple[str, ...]:
        kw = self._kind(kind)
        if status not in kw.states:
            raise ValidationError(
                f"状态 {status!r} 不属于 kind={kind}",
                details={"kind": kind, "status": status, "allowed": list(kw.states)},
            )
        return tuple(kw.transitions[status])

    def check(
        self,
        kind: str,
        src: str,
        dst: str,
        *,
        item: str | None = None,
        context: GateContext | None = None,
    ) -> None:
        """Raise on an illegal transition or an unmet gate; return None if OK."""
        kw = self._kind(kind)
        if src not in kw.states:
            raise ValidationError(
                f"当前状态 {src!r} 不属于 kind={kind}",
                details={"kind": kind, "status": src, "allowed": list(kw.states)},
            )
        if dst not in kw.states:
            raise ValidationError(
                f"目标状态 {dst!r} 不属于 kind={kind}",
                details={"kind": kind, "status": dst, "allowed": list(kw.states)},
            )

        allowed_next = tuple(kw.transitions[src])
        if dst not in allowed_next:
            label = f"{item} " if item else ""
            raise WorkflowIllegalTransition(
                f"{label}不能从 {src} 转到 {dst}。允许：{list(allowed_next)}。",
                details={
                    "kind": kind,
                    "from": src,
                    "to": dst,
                    "allowed_transitions": list(allowed_next),
                },
            )

        gate = kw.gates.get(dst)
        if gate is not None:
            self._check_gate(kind, src, dst, gate, item, context or GateContext(), allowed_next)

    def _check_gate(
        self,
        kind: str,
        src: str,
        dst: str,
        gate: GateSpec,
        item: str | None,
        ctx: GateContext,
        allowed_next: tuple[str, ...],
    ) -> None:
        label = item or kind
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

        if not reasons:
            return

        details = {
            "item": item,
            "kind": kind,
            "from": src,
            "target": dst,
            "blocking_children": blocking,
            "allowed_transitions": list(allowed_next),
            "hint": "先完成或取消阻塞项，再重试；必要时用 comment_add 通知负责人。",
            **extra,
        }
        raise WorkflowGateBlocked(
            f"{label} 不能进入 {dst}：{'；'.join(reasons)}",
            details=details,
        )
