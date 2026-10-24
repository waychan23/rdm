"""Pydantic schema for resources/workflow.yml — validated and frozen at load."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class GateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    children_all_terminal: bool | None = None
    min_children: int | None = None
    no_nonterminal_sprint_items: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> GateSpec:
        if self.min_children is not None and self.min_children < 1:
            raise ValueError("min_children must be >= 1")
        if not any(
            v is not None
            for v in (
                self.children_all_terminal,
                self.min_children,
                self.no_nonterminal_sprint_items,
            )
        ):
            raise ValueError("gate must declare at least one condition")
        return self


class KindWorkflow(BaseModel):
    model_config = ConfigDict(frozen=True)

    states: tuple[str, ...]
    initial: str
    terminal: tuple[str, ...]
    transitions: dict[str, tuple[str, ...]]
    gates: dict[str, GateSpec] = {}

    @model_validator(mode="after")
    def _validate(self) -> KindWorkflow:
        state_set = set(self.states)
        if len(self.states) != len(state_set):
            raise ValueError("states must be unique")
        if self.initial not in state_set:
            raise ValueError(f"initial {self.initial!r} not in states")
        if unknown_terminal := [s for s in self.terminal if s not in state_set]:
            raise ValueError(f"terminal states not in states: {unknown_terminal}")
        if set(self.transitions) != state_set:
            raise ValueError("transitions must define an entry for every state")
        for src, targets in self.transitions.items():
            unknown = [t for t in targets if t not in state_set]
            if unknown:
                raise ValueError(f"transition {src} -> unknown states {unknown}")
        unknown_gate_targets = [s for s in self.gates if s not in state_set]
        if unknown_gate_targets:
            raise ValueError(f"gates attached to unknown states: {unknown_gate_targets}")
        return self


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int
    kinds: dict[str, KindWorkflow]

    @model_validator(mode="after")
    def _validate(self) -> WorkflowSpec:
        if not self.kinds:
            raise ValueError("workflow must define at least one kind")
        return self

    def kind(self, kind: str) -> KindWorkflow:
        return self.kinds[kind]

    def has_kind(self, kind: str) -> bool:
        return kind in self.kinds
