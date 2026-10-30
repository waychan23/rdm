"""Pydantic schema for resources/workflow.json5 — validated and frozen at load.

v3 introduces named transition edges ("steps") with executor types, counted
executor ranges, note requirements, field gates and optional task execution.
Legacy ``transitions`` input is normalized into ``steps`` so older specs keep
loading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StepMode = Literal["direct", "approval", "task"]
ActorSource = Literal["assignee", "participants", "managers", "reviewers"]
NoteRequirement = Literal["optional", "required"]
CustomFieldType = Literal["text", "number", "user"]

STEP_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")

# Fields that every kind can reference in a required_fields gate. Built-in
# reviewer/review_content still have to be enabled on the effective workflow.
MASTER_FIELD_KEYS = frozenset({"title", "description_md"})
BUILTIN_FIELD_KEYS = frozenset({"reviewer", "review_content"})
KIND_FIELD_KEYS: dict[str, frozenset[str]] = {
    "epic": frozenset(),
    "story": frozenset({"acceptance_criteria_md"}),
    "issue": frozenset(
        {
            "severity",
            "environment",
            "repro_steps_md",
            "expected_behavior_md",
            "actual_behavior_md",
            "source_story_id",
        }
    ),
    "task": frozenset({"task_type", "est_work_hours", "actual_work_hours", "code_branch"}),
    "sprint": frozenset({"name", "goal_md", "start_date", "end_date", "manager_user_id"}),
}
# Step tasks are regular child work items; epic can now contain tasks too.
TASK_CHILD_PARENT_KINDS = frozenset({"epic", "story", "issue", "task"})


class GateSpec(BaseModel):
    """Gate conditions. Field-wise merge against kind-level defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    children_all_terminal: bool | None = None
    min_children: int | None = None
    no_nonterminal_sprint_items: bool | None = None
    required_fields: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _validate(self) -> GateSpec:
        # min_children: 0 is an explicit "no constraint" override when a step
        # disables a kind-level default.
        if self.min_children is not None and self.min_children < 0:
            raise ValueError("min_children must be >= 0")
        if self.required_fields is not None:
            if len(set(self.required_fields)) != len(self.required_fields):
                raise ValueError("required_fields must be unique")
        return self

    def is_empty(self) -> bool:
        basic = any(
            value is not None
            for value in (
                self.children_all_terminal,
                self.min_children,
                self.no_nonterminal_sprint_items,
            )
        )
        return not basic and not self.required_fields


class ExecutorRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min: int = 1
    # None means "as many as the candidate pool allows".
    max: int | None = 1

    @model_validator(mode="after")
    def _validate(self) -> ExecutorRange:
        if self.min < 1:
            raise ValueError("executors.min must be >= 1")
        if self.max is not None and self.max < self.min:
            raise ValueError("executors.max must be >= executors.min")
        return self


class TaskStepSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str = Field(min_length=1, max_length=50)
    title: str = "{display_id} {name}"
    complete_on: str = "DONE"


class StepSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    name: str = Field(min_length=1, max_length=100)
    to: str
    mode: StepMode = "direct"
    actors: tuple[ActorSource, ...] = ("assignee",)
    executors: ExecutorRange = Field(default_factory=ExecutorRange)
    note: NoteRequirement = "optional"
    gates: GateSpec | None = None
    tasks: TaskStepSpec | None = None

    @model_validator(mode="after")
    def _validate(self) -> StepSpec:
        if not STEP_KEY_RE.fullmatch(self.key):
            raise ValueError(f"step key {self.key!r} must match {STEP_KEY_RE.pattern}")
        if not self.actors:
            raise ValueError(f"step {self.key}: actors must not be empty")
        if len(set(self.actors)) != len(self.actors):
            raise ValueError(f"step {self.key}: actors must be unique")
        if self.mode == "direct":
            if self.executors.min != 1 or self.executors.max != 1:
                raise ValueError(f"step {self.key}: direct mode requires executors {{min:1,max:1}}")
            if self.tasks is not None:
                raise ValueError(f"step {self.key}: direct mode cannot create tasks")
        elif self.mode == "task":
            if self.tasks is None:
                raise ValueError(f"step {self.key}: task mode requires tasks")
            if self.note == "required":
                raise ValueError(f"step {self.key}: task mode cannot require a step note")
        else:  # approval
            if self.tasks is not None:
                raise ValueError(f"step {self.key}: approval mode cannot create tasks")
        return self


class CustomFieldSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str = Field(min_length=1, max_length=100)
    type: CustomFieldType
    multiple: bool = False

    @model_validator(mode="after")
    def _validate(self) -> CustomFieldSpec:
        if not FIELD_KEY_RE.fullmatch(self.key):
            raise ValueError(f"custom field key {self.key!r} must match {FIELD_KEY_RE.pattern}")
        if self.type != "user" and self.multiple:
            raise ValueError(f"custom field {self.key}: multiple is only valid for type=user")
        return self


class FieldsSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer: bool = False
    review_content: bool = False
    custom: tuple[CustomFieldSpec, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> FieldsSpec:
        keys = [field.key for field in self.custom]
        if len(set(keys)) != len(keys):
            raise ValueError("custom field keys must be unique")
        reserved = BUILTIN_FIELD_KEYS | MASTER_FIELD_KEYS
        overlap = sorted(reserved.intersection(keys))
        if overlap:
            raise ValueError(f"custom field keys collide with reserved fields: {overlap}")
        return self


def _legacy_steps(transitions: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    steps: dict[str, list[dict[str, Any]]] = {}
    for src, targets in transitions.items():
        items: list[dict[str, Any]] = []
        for target in targets or ():
            target = str(target)
            key = "TO_" + re.sub(r"[^A-Z0-9_]", "_", target.upper())
            items.append({"key": key, "name": target, "to": target})
        steps[src] = items
    return steps


def _normalize_steps_input(data: Any) -> Any:
    """Accept legacy ``transitions: {src: [targets]}`` as step definitions."""
    if not isinstance(data, dict):
        return data
    has_steps = data.get("steps") is not None
    has_transitions = data.get("transitions") is not None
    if has_steps and has_transitions:
        raise ValueError("declare either steps or transitions, not both")
    if not has_steps and has_transitions:
        data = dict(data)
        data["steps"] = _legacy_steps(data.pop("transitions"))
    return data


class SubtypeWorkflow(BaseModel):
    """Partial workflow override for a task type; resolved against its parent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str | None = None
    states: tuple[str, ...] | None = None
    initial: str | None = None
    terminal: tuple[str, ...] | None = None
    steps: dict[str, tuple[StepSpec, ...]] | None = None
    gates: dict[str, GateSpec] | None = None
    fields: FieldsSpec | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _normalize_steps_input(data)

    @model_validator(mode="after")
    def _validate(self) -> SubtypeWorkflow:
        if self.states is None:
            if self.initial is not None or self.terminal is not None:
                raise ValueError("initial/terminal require an explicit states list")
        else:
            if len(set(self.states)) != len(self.states):
                raise ValueError("subtype states must be unique")
            if self.initial is None or self.terminal is None:
                raise ValueError("subtype states require initial and terminal")
            if self.initial not in self.states:
                raise ValueError("subtype initial not in states")
            if any(state not in self.states for state in self.terminal):
                raise ValueError("subtype terminal states not in states")
            if self.steps is None:
                raise ValueError("subtype declaring states must declare steps for every state")
            if set(self.steps) != set(self.states):
                raise ValueError(
                    "subtype declaring states must declare steps for exactly those states"
                )
        return self


class KindWorkflow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str | None = None
    states: tuple[str, ...]
    initial: str
    terminal: tuple[str, ...]
    steps: dict[str, tuple[StepSpec, ...]]
    gates: dict[str, GateSpec] = {}
    fields: FieldsSpec = Field(default_factory=FieldsSpec)
    subtypes: dict[str, SubtypeWorkflow] = {}

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _normalize_steps_input(data)

    @model_validator(mode="after")
    def _validate(self) -> KindWorkflow:
        state_set = set(self.states)
        if len(self.states) != len(state_set):
            raise ValueError("states must be unique")
        if self.initial not in state_set:
            raise ValueError(f"initial {self.initial!r} not in states")
        if unknown_terminal := [s for s in self.terminal if s not in state_set]:
            raise ValueError(f"terminal states not in states: {unknown_terminal}")
        if set(self.steps) != state_set:
            raise ValueError("steps must define an entry for every state")
        for src, steps in self.steps.items():
            keys: set[str] = set()
            for step in steps:
                if step.key in keys:
                    raise ValueError(f"duplicate step key {step.key!r} in state {src}")
                keys.add(step.key)
                if step.to not in state_set:
                    raise ValueError(f"step {src}/{step.key} targets unknown state {step.to}")
        unknown_gate_targets = [s for s in self.gates if s not in state_set]
        if unknown_gate_targets:
            raise ValueError(f"gates attached to unknown states: {unknown_gate_targets}")
        for target, gate in self.gates.items():
            if gate.is_empty():
                raise ValueError(f"gate for {target} must declare at least one condition")
        return self


@dataclass(frozen=True)
class ResolvedKindWorkflow:
    """Effective workflow for a concrete (kind, task_type) pair."""

    kind: str
    task_type: str | None
    label: str
    states: tuple[str, ...]
    initial: str
    terminal: tuple[str, ...]
    steps: dict[str, tuple[StepSpec, ...]]
    gates: dict[str, GateSpec]
    fields: FieldsSpec

    def steps_from(self, state: str) -> tuple[StepSpec, ...]:
        return tuple(self.steps[state])

    def allowed(self, state: str) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for step in self.steps[state]:
            seen.setdefault(step.to, None)
        return tuple(seen)

    def all_field_keys(self) -> frozenset[str]:
        keys = set(MASTER_FIELD_KEYS) | set(KIND_FIELD_KEYS.get(self.kind, ()))
        if self.fields.reviewer:
            keys.add("reviewer")
        if self.fields.review_content:
            keys.add("review_content")
        keys.update(field.key for field in self.fields.custom)
        return frozenset(keys)


def _merge_steps(
    base: dict[str, tuple[StepSpec, ...]],
    override: dict[str, tuple[StepSpec, ...]] | None,
) -> dict[str, tuple[StepSpec, ...]]:
    if not override:
        return dict(base)
    merged = dict(base)
    for state, steps in override.items():
        merged[state] = tuple(steps)
    return merged


def _merge_fields(base: FieldsSpec, override: FieldsSpec | None) -> FieldsSpec:
    if override is None:
        return base
    explicit = override.model_fields_set
    custom: dict[str, CustomFieldSpec] = {field.key: field for field in base.custom}
    for field in override.custom:
        custom[field.key] = field
    return FieldsSpec(
        reviewer=override.reviewer if "reviewer" in explicit else base.reviewer,
        review_content=(
            override.review_content if "review_content" in explicit else base.review_content
        ),
        custom=tuple(custom.values()),
    )


def merge_gates(default: GateSpec | None, override: GateSpec | None) -> GateSpec | None:
    """Merge edge gates over kind defaults field by field."""
    if default is None:
        return override
    if override is None:
        return default
    data = default.model_dump()
    for field in override.model_fields_set:
        data[field] = getattr(override, field)
    return GateSpec.model_validate(data)


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    task_types: dict[str, str] = {}
    kinds: dict[str, KindWorkflow]

    @model_validator(mode="after")
    def _validate(self) -> WorkflowSpec:
        if not self.kinds:
            raise ValueError("workflow must define at least one kind")
        if "task" in self.kinds:
            subtypes = set(self.kinds["task"].subtypes)
            unknown = sorted(subtypes - set(self.task_types))
            if unknown:
                raise ValueError(f"task subtypes missing from task_types: {unknown}")
        for kind in self.kinds:
            self.resolve(kind)
            for subtype in self.kinds[kind].subtypes:
                self.resolve(kind, subtype)
        return self

    def kind(self, kind: str) -> KindWorkflow:
        return self.kinds[kind]

    def has_kind(self, kind: str) -> bool:
        return kind in self.kinds

    def resolve(
        self,
        kind: str,
        task_type: str | None = None,
        *,
        _seen: frozenset[tuple[str, str | None]] = frozenset(),
    ) -> ResolvedKindWorkflow:
        """Return the effective workflow, merging a task subtype when present."""
        if kind not in self.kinds:
            raise ValueError(f"unknown kind {kind!r}")
        key = (kind, task_type if kind == "task" else None)
        if key in _seen:
            raise ValueError(f"workflow resolution cycle at {key}")
        base = self.kinds[kind]
        subtype_key = key[1]
        subtype = base.subtypes.get(subtype_key) if subtype_key is not None else None
        if subtype is None:
            resolved = ResolvedKindWorkflow(
                kind=kind,
                task_type=key[1],
                label=base.label or kind,
                states=base.states,
                initial=base.initial,
                terminal=base.terminal,
                steps=dict(base.steps),
                gates=dict(base.gates),
                fields=base.fields,
            )
            self._validate_resolved(resolved, _seen | {key})
            return resolved

        states = subtype.states or base.states
        initial = subtype.initial if subtype.states is not None else base.initial
        terminal = subtype.terminal if subtype.states is not None else base.terminal
        assert initial is not None and terminal is not None  # validated above
        steps = (
            dict(subtype.steps or {})
            if subtype.states is not None
            else _merge_steps(base.steps, subtype.steps)
        )
        gates = dict(subtype.gates) if subtype.gates is not None else dict(base.gates)
        fields = _merge_fields(base.fields, subtype.fields)
        resolved = ResolvedKindWorkflow(
            kind=kind,
            task_type=key[1],
            label=subtype.label or base.label or kind,
            states=tuple(states),
            initial=initial,
            terminal=tuple(terminal),
            steps=steps,
            gates=gates,
            fields=fields,
        )
        self._validate_resolved(resolved, _seen | {key})
        return resolved

    def _validate_resolved(
        self,
        resolved: ResolvedKindWorkflow,
        seen: frozenset[tuple[str, str | None]],
    ) -> None:
        state_set = set(resolved.states)
        if len(resolved.states) != len(state_set):
            raise ValueError(f"{resolved.kind}: states must be unique")
        if resolved.initial not in state_set:
            raise ValueError(f"{resolved.kind}: initial {resolved.initial!r} not in states")
        if any(state not in state_set for state in resolved.terminal):
            raise ValueError(f"{resolved.kind}: terminal states not in states")
        if set(resolved.steps) != state_set:
            raise ValueError(f"{resolved.kind}: steps must define every state")
        allowed_fields = resolved.all_field_keys()
        for src, steps in resolved.steps.items():
            keys: set[str] = set()
            for step in steps:
                if step.key in keys:
                    raise ValueError(f"{resolved.kind}/{src}: duplicate step key {step.key!r}")
                keys.add(step.key)
                if step.to not in state_set:
                    raise ValueError(
                        f"{resolved.kind}/{src}/{step.key}: target {step.to} not in states"
                    )
                gate = merge_gates(resolved.gates.get(step.to), step.gates)
                if gate is not None:
                    for required_field in gate.required_fields or ():
                        if required_field not in allowed_fields:
                            raise ValueError(
                                f"{resolved.kind}/{src}/{step.key}: required field "
                                f"{required_field!r} is not enabled or declared"
                            )
                if step.mode == "task":
                    assert step.tasks is not None
                    if resolved.kind not in TASK_CHILD_PARENT_KINDS:
                        raise ValueError(
                            f"{resolved.kind}/{src}/{step.key}: task steps require a "
                            "parent kind that can contain tasks"
                        )
                    if step.tasks.type not in self.task_types:
                        raise ValueError(
                            f"{resolved.kind}/{src}/{step.key}: unknown task type "
                            f"{step.tasks.type!r}"
                        )
                    child = self.resolve("task", step.tasks.type, _seen=seen)
                    if step.tasks.complete_on not in child.terminal:
                        raise ValueError(
                            f"{resolved.kind}/{src}/{step.key}: complete_on "
                            f"{step.tasks.complete_on!r} is not terminal for task type "
                            f"{step.tasks.type!r}"
                        )
        for target, gate in resolved.gates.items():
            if target not in state_set:
                raise ValueError(f"{resolved.kind}: gate targets unknown state {target}")
            if gate.is_empty():
                raise ValueError(
                    f"{resolved.kind}: gate for {target} must declare at least one condition"
                )
        for custom_field in resolved.fields.custom:
            if custom_field.key in MASTER_FIELD_KEYS:
                raise ValueError(
                    f"{resolved.kind}: custom field {custom_field.key!r} collides with a "
                    "master field"
                )
