"""Pydantic schema for resources/workflow.json5 — validated and frozen at load.

v3 introduces named transition edges ("steps") with executor types, counted
executor ranges, note requirements, field gates and optional task execution.
Legacy ``transitions`` input is normalized into ``steps`` so older specs keep
loading.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

StepMode = Literal["direct", "approval", "task"]
TriggerErrorPolicy = Literal["fail", "ignore"]
ActorSource = Literal["assignee", "participants", "managers", "reviewers", "project_members"]
NoteRequirement = Literal["optional", "required"]
CustomFieldType = Literal["text", "number", "user"]

STEP_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
DEF_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")

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


class TriggerTarget(BaseModel):
    """Guard and action for the item whose status the rule changes (§17.146).

    Exactly one action selects the transition: ``to`` (target state; must be
    reachable by a unique direct step) or ``step`` (step key; only direct steps
    execute automatically). ``to`` and ``step`` may be combined as a sanity
    check; a mismatch skips the rule.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    # Absent means "any non-terminal state other than the target".
    from_: tuple[str, ...] = Field(default=(), alias="from")
    to: str | None = Field(default=None, min_length=1)
    step: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> TriggerTarget:
        if len(set(self.from_)) != len(self.from_):
            raise ValueError("trigger target from must be unique")
        if self.to is None and self.step is None:
            raise ValueError("trigger target requires to or step")
        if self.step is not None and not STEP_KEY_RE.fullmatch(self.step):
            raise ValueError(f"trigger target step {self.step!r} must be a valid step key")
        return self


@dataclass(frozen=True)
class StatusFlags:
    """Workflow-derived flags for one item's current status (§17.148)."""

    start: bool
    terminal: bool
    main_terminal: bool
    side_terminal: bool


class StatusPredicate(BaseModel):
    """Current-status predicate for trigger.from / trigger.to (§17.147)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Empty means any status.
    statuses: tuple[str, ...] = ()
    # None means any; true/false pins the workflow initial state.
    start: bool | None = None
    # None means any terminality; true/false pins it.
    terminal: bool | None = None
    main_terminal: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("main_terminal", "mainTerminal"),
    )
    side_terminal: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("side_terminal", "sideTerminal"),
    )

    @model_validator(mode="after")
    def _validate(self) -> StatusPredicate:
        if len(set(self.statuses)) != len(self.statuses):
            raise ValueError("status predicate statuses must be unique")
        return self

    def matches(self, status: str, flags: StatusFlags) -> bool:
        if self.statuses and status not in self.statuses:
            return False
        if self.start is not None and flags.start != self.start:
            return False
        if self.terminal is not None and flags.terminal != self.terminal:
            return False
        if self.main_terminal is not None and flags.main_terminal != self.main_terminal:
            return False
        if self.side_terminal is not None and flags.side_terminal != self.side_terminal:
            return False
        return True


class TriggerEvent(BaseModel):
    """The direct-child status change that fires a rule (§17.145/§17.147).

    ``kinds`` / ``tasktypes`` filter the changed child; ``from`` / ``to`` are
    status predicates (same shape as when clauses) so rules can span kinds with
    different concrete state names. Bare strings/lists are accepted as
    ``statuses`` shorthand.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    kinds: tuple[str, ...] = ()
    # Accept both spellings; serialize the canonical "tasktypes".
    task_types: tuple[str, ...] = Field(
        default=(),
        validation_alias=AliasChoices("tasktypes", "task_types"),
        serialization_alias="tasktypes",
    )
    from_: StatusPredicate = Field(default_factory=StatusPredicate, alias="from")
    to: StatusPredicate = Field(default_factory=StatusPredicate)

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _normalize_predicate(cls, value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, str):
            return {"statuses": [value]}
        if isinstance(value, (list, tuple)):
            return {"statuses": list(value)}
        return value

    @model_validator(mode="after")
    def _validate(self) -> TriggerEvent:
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("trigger.kinds must be unique")
        if len(set(self.task_types)) != len(self.task_types):
            raise ValueError("trigger.tasktypes must be unique")
        return self

    def matches(
        self,
        child_kind: str,
        child_task_type: str | None,
        from_state: str,
        to_state: str,
        *,
        from_flags: StatusFlags,
        to_flags: StatusFlags,
    ) -> bool:
        if self.kinds and child_kind not in self.kinds:
            return False
        if self.task_types and (child_task_type is None or child_task_type not in self.task_types):
            return False
        if not self.from_.matches(from_state, from_flags):
            return False
        if not self.to.matches(to_state, to_flags):
            return False
        return True


class ChildQuantifier(BaseModel):
    """Selector + predicate for one any/all clause (§17.145).

    A clause first selects direct children by ``kinds`` / ``tasktypes``, then
    checks their current status against ``statuses`` / ``start`` / ``terminal``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    kinds: tuple[str, ...] = ()
    task_types: tuple[str, ...] = Field(
        default=(),
        validation_alias=AliasChoices("tasktypes", "task_types"),
        serialization_alias="tasktypes",
    )
    # Empty means any status.
    statuses: tuple[str, ...] = ()
    # None means any; true/false pins the item's workflow initial state.
    start: bool | None = None
    # None means any terminality; true/false pins it.
    terminal: bool | None = None
    main_terminal: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("main_terminal", "mainTerminal"),
    )
    side_terminal: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("side_terminal", "sideTerminal"),
    )
    # Additional conjunction applied to the same selected child; recursive.
    and_: ChildQuantifier | None = Field(default=None, alias="and")

    @model_validator(mode="after")
    def _validate(self) -> ChildQuantifier:
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("quantifier kinds must be unique")
        if len(set(self.task_types)) != len(self.task_types):
            raise ValueError("quantifier tasktypes must be unique")
        if len(set(self.statuses)) != len(self.statuses):
            raise ValueError("quantifier statuses must be unique")
        return self

    def selects(self, kind: str, task_type: str | None) -> bool:
        if self.kinds and kind not in self.kinds:
            return False
        if self.task_types and (task_type is None or task_type not in self.task_types):
            return False
        return True

    def matches(self, status: str, flags: StatusFlags) -> bool:
        if self.statuses and status not in self.statuses:
            return False
        if self.start is not None and flags.start != self.start:
            return False
        if self.terminal is not None and flags.terminal != self.terminal:
            return False
        if self.main_terminal is not None and flags.main_terminal != self.main_terminal:
            return False
        if self.side_terminal is not None and flags.side_terminal != self.side_terminal:
            return False
        return True

    def matches_chain(
        self,
        kind: str,
        task_type: str | None,
        status: str,
        flags: StatusFlags,
    ) -> bool:
        if not self.selects(kind, task_type):
            return False
        if not self.matches(status, flags):
            return False
        if self.and_ is not None and not self.and_.matches_chain(kind, task_type, status, flags):
            return False
        return True


class TriggerWhen(BaseModel):
    """Quantified condition over the direct children of the item that changes.

    ``any`` = at least one child selected by that clause matches;
    ``all`` = every child selected by that clause matches. The clauses are
    AND-ed; an empty selected set never satisfies a clause.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    any: ChildQuantifier | None = None
    all: ChildQuantifier | None = None

    @model_validator(mode="after")
    def _validate(self) -> TriggerWhen:
        if self.any is None and self.all is None:
            raise ValueError("when requires any or all")
        return self


_SELECTOR_KEYS = ("kinds", "task_types", "tasktypes")


def _migrate_trigger_data(data: Any) -> Any:
    """Map pre-release trigger shapes onto the §17.145 rule shape."""
    if not isinstance(data, dict):
        return data
    when = data.get("when")
    children = data.pop("children", None)
    legacy_all = data.pop("all_children_terminal", None)
    legacy_any = data.pop("any_children_terminal", None)
    legacy_min = data.pop("min_children_terminal", None)

    # Older shapes used when.from/to as the triggering child event; that is
    # now the dedicated ``trigger`` key.
    if isinstance(when, dict) and ("from" in when or "to" in when):
        if "trigger" in data:
            raise ValueError("declare either trigger or a legacy event when, not both")
        data["trigger"] = when
        when = None
    if children is not None:
        if when is not None:
            raise ValueError('use "when" for child quantifiers; "children" is no longer a key')
        when = children

    if legacy_all is not None or legacy_any is not None or legacy_min is not None:
        when = dict(when or {})
        if legacy_all:
            when["all"] = {**(when.get("all") or {}), "terminal": True}
        if legacy_any:
            when["any"] = {**(when.get("any") or {}), "terminal": True}
        if legacy_min is not None:
            raise ValueError("min_children_terminal was removed; use any/all clauses")

    if when is not None:
        if not isinstance(when, dict):
            raise ValueError("when must be an object")
        if "min_terminal" in when:
            raise ValueError("when.min_terminal was removed; use any/all clauses")
        for key in ("any", "all"):
            value = when.get(key)
            if isinstance(value, list):
                raise ValueError("when.any/all are quantifier objects, not clause lists")
            if value is not None and not isinstance(value, dict):
                raise ValueError(f"when.{key} must be an object")
        # Previous shapes had one shared selector at the when level; move it
        # into each clause.
        selectors: dict[str, Any] = {}
        for key in _SELECTOR_KEYS:
            if key in when:
                value = when.pop(key)
                selectors["task_types" if key == "tasktypes" else key] = value
        if selectors:
            for key in ("any", "all"):
                clause = when.get(key)
                if clause is not None:
                    when[key] = {**selectors, **clause}
        data["when"] = when
    return data


class ParentTriggerSpec(BaseModel):
    """A rule declared on the child's definition (§17.137/§17.145).

    ``trigger`` matches the changed child event; ``when`` quantifies the
    parent's direct children at that moment; ``parent`` is the state
    guard/target. At least one of trigger/when is required.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    trigger: TriggerEvent | None = None
    when: TriggerWhen | None = None
    parent: TriggerTarget
    # Unexpected errors: "fail" rolls back the main operation; "ignore" logs
    # the error and rolls back only this rule's partial work (savepoint).
    on_error: TriggerErrorPolicy = "fail"

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: Any) -> Any:
        return _migrate_trigger_data(data)

    @model_validator(mode="after")
    def _validate(self) -> ParentTriggerSpec:
        if self.trigger is None and self.when is None:
            raise ValueError("trigger rule requires trigger or when")
        return self


class ChildTriggerSpec(BaseModel):
    """A child-set condition declared on the item that changes (§17.138).

    Declared on the **parent** definition, so one rule can aggregate children
    of different kinds (e.g. a story with task and issue children). The
    declaring item is addressed as ``self``; ``parent_triggers`` remains the
    child-side counterpart.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    trigger: TriggerEvent | None = None
    when: TriggerWhen | None = None
    self_: TriggerTarget = Field(alias="self")
    on_error: TriggerErrorPolicy = "fail"

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: Any) -> Any:
        return _migrate_trigger_data(data)

    @model_validator(mode="after")
    def _validate(self) -> ChildTriggerSpec:
        if self.trigger is None and self.when is None:
            raise ValueError("trigger rule requires trigger or when")
        return self


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
    # Optional English display name (§17.115); falls back to name.
    name_en: str | None = Field(default=None, max_length=100)
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
    label_en: str | None = Field(default=None, max_length=100)
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


def _validate_graph(
    *,
    states: tuple[str, ...],
    initial: str,
    terminal: tuple[str, ...],
    steps: dict[str, tuple[StepSpec, ...]],
    gates: dict[str, GateSpec],
) -> None:
    """Structural checks shared by inline kind workflows and named definitions."""
    state_set = set(states)
    if len(states) != len(state_set):
        raise ValueError("states must be unique")
    if initial not in state_set:
        raise ValueError(f"initial {initial!r} not in states")
    if unknown_terminal := [s for s in terminal if s not in state_set]:
        raise ValueError(f"terminal states not in states: {unknown_terminal}")
    if set(steps) != state_set:
        raise ValueError("steps must define an entry for every state")
    for src, src_steps in steps.items():
        keys: set[str] = set()
        for step in src_steps:
            if step.key in keys:
                raise ValueError(f"duplicate step key {step.key!r} in state {src}")
            keys.add(step.key)
            if step.to not in state_set:
                raise ValueError(f"step {src}/{step.key} targets unknown state {step.to}")
    unknown_gate_targets = [s for s in gates if s not in state_set]
    if unknown_gate_targets:
        raise ValueError(f"gates attached to unknown states: {unknown_gate_targets}")
    for target, gate in gates.items():
        if gate.is_empty():
            raise ValueError(f"gate for {target} must declare at least one condition")


def classify_terminal(
    terminal: Sequence[str],
    main: Sequence[str] | None,
    side: Sequence[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split terminal states into normal (main) and abnormal (side) (§17.148).

    Neither list declared -> every terminal state is main. Only one declared ->
    the other is the remainder. Both declared -> must be disjoint and cover all
    terminal states. Order follows ``terminal``.
    """
    terminal_list = list(terminal)
    terminal_set = set(terminal_list)
    main_set = set(main) if main is not None else None
    side_set = set(side) if side is not None else None
    if main_set is None and side_set is None:
        return tuple(terminal_list), ()
    if main_set is None:
        assert side_set is not None
        main_set = terminal_set - side_set
    elif side_set is None:
        side_set = terminal_set - main_set
    assert main_set is not None and side_set is not None
    if not main_set <= terminal_set or not side_set <= terminal_set:
        raise ValueError("main_terminal/side_terminal must be subsets of terminal")
    if main_set & side_set:
        raise ValueError("main_terminal and side_terminal must be disjoint")
    if main_set | side_set != terminal_set:
        raise ValueError("main_terminal and side_terminal must cover all terminal states")
    return (
        tuple(state for state in terminal_list if state in main_set),
        tuple(state for state in terminal_list if state in side_set),
    )


class SubtypeWorkflow(BaseModel):
    """Partial workflow override for a task type; resolved against its parent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str | None = None
    label_en: str | None = None
    states: tuple[str, ...] | None = None
    initial: str | None = None
    terminal: tuple[str, ...] | None = None
    main_terminal: tuple[str, ...] | None = Field(
        default=None,
        validation_alias=AliasChoices("main_terminal", "mainTerminal"),
    )
    side_terminal: tuple[str, ...] | None = Field(
        default=None,
        validation_alias=AliasChoices("side_terminal", "sideTerminal"),
    )
    steps: dict[str, tuple[StepSpec, ...]] | None = None
    gates: dict[str, GateSpec] | None = None
    fields: FieldsSpec | None = None
    # Declaring the key replaces the kind-level rules; absent inherits them.
    parent_triggers: tuple[ParentTriggerSpec, ...] | None = None
    child_triggers: tuple[ChildTriggerSpec, ...] | None = None

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
            classify_terminal(self.terminal, self.main_terminal, self.side_terminal)
        return self


class KindWorkflow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str | None = None
    label_en: str | None = None
    states: tuple[str, ...]
    initial: str
    terminal: tuple[str, ...]
    main_terminal: tuple[str, ...] | None = Field(
        default=None,
        validation_alias=AliasChoices("main_terminal", "mainTerminal"),
    )
    side_terminal: tuple[str, ...] | None = Field(
        default=None,
        validation_alias=AliasChoices("side_terminal", "sideTerminal"),
    )
    steps: dict[str, tuple[StepSpec, ...]]
    gates: dict[str, GateSpec] = {}
    fields: FieldsSpec = Field(default_factory=FieldsSpec)
    parent_triggers: tuple[ParentTriggerSpec, ...] = ()
    child_triggers: tuple[ChildTriggerSpec, ...] = ()
    subtypes: dict[str, SubtypeWorkflow] = {}

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _normalize_steps_input(data)

    @model_validator(mode="after")
    def _validate(self) -> KindWorkflow:
        _validate_graph(
            states=self.states,
            initial=self.initial,
            terminal=self.terminal,
            steps=self.steps,
            gates=self.gates,
        )
        classify_terminal(self.terminal, self.main_terminal, self.side_terminal)
        return self


class NamedWorkflow(BaseModel):
    """A reusable workflow graph declared under top-level ``workflow_defs``.

    Kinds and task subtypes reference one by name with ``use``; the loader
    expands it into an inline definition before validation, so downstream code
    only ever sees resolved graphs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    states: tuple[str, ...]
    initial: str
    terminal: tuple[str, ...]
    main_terminal: tuple[str, ...] | None = Field(
        default=None,
        validation_alias=AliasChoices("main_terminal", "mainTerminal"),
    )
    side_terminal: tuple[str, ...] | None = Field(
        default=None,
        validation_alias=AliasChoices("side_terminal", "sideTerminal"),
    )
    steps: dict[str, tuple[StepSpec, ...]]
    gates: dict[str, GateSpec] = {}
    fields: FieldsSpec = Field(default_factory=FieldsSpec)
    parent_triggers: tuple[ParentTriggerSpec, ...] = ()
    child_triggers: tuple[ChildTriggerSpec, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _normalize_steps_input(data)

    @model_validator(mode="after")
    def _validate(self) -> NamedWorkflow:
        _validate_graph(
            states=self.states,
            initial=self.initial,
            terminal=self.terminal,
            steps=self.steps,
            gates=self.gates,
        )
        classify_terminal(self.terminal, self.main_terminal, self.side_terminal)
        return self


def _expand_ref(
    raw: Any,
    defs: dict[str, dict[str, Any]],
    *,
    where: str,
    is_kind: bool,
) -> Any:
    """Replace ``use: name`` with the referenced definition plus local overrides."""
    if not isinstance(raw, dict):
        return raw
    body = dict(raw)
    use = body.pop("use", None)
    if use is not None:
        if not isinstance(use, str) or use not in defs:
            raise ValueError(f"{where}: unknown workflow_defs reference {use!r}")
        conflict = sorted(set(body).intersection({"states", "initial", "terminal", "steps"}))
        if conflict:
            raise ValueError(
                f"{where}: cannot declare {', '.join(conflict)} alongside use; "
                f"override them in workflow_defs.{use}"
            )
        # Definition body first; local keys (label/gates/fields/subtypes) win.
        body = {**defs[use], **body}
    if is_kind and isinstance(body.get("subtypes"), dict):
        body["subtypes"] = {
            name: _expand_ref(sub, defs, where=f"{where}.subtypes.{name}", is_kind=False)
            for name, sub in body["subtypes"].items()
        }
    return body


def _expand_workflow_defs(raw: Any) -> Any:
    """Expand named-definition references across all kinds and subtypes."""
    if not isinstance(raw, dict):
        return raw
    defs_raw = raw.get("workflow_defs") or {}
    if not isinstance(defs_raw, dict):
        raise ValueError("workflow_defs must be an object")
    defs: dict[str, dict[str, Any]] = {}
    for name, body in defs_raw.items():
        if not isinstance(name, str) or not DEF_NAME_RE.fullmatch(name):
            raise ValueError(f"workflow_defs key {name!r} must match {DEF_NAME_RE.pattern}")
        normalized = _normalize_steps_input(body)
        if not isinstance(normalized, dict):
            raise ValueError(f"workflow_defs.{name} must be an object")
        if "use" in normalized:
            raise ValueError(
                f"workflow_defs.{name}: definitions cannot reference other definitions"
            )
        try:
            definition = NamedWorkflow.model_validate(normalized)
        except PydanticValidationError as exc:
            raise ValueError(f"workflow_defs.{name} is invalid: {exc}") from exc
        defs[name] = definition.model_dump()
    data = dict(raw)
    kinds = data.get("kinds")
    if isinstance(kinds, dict):
        data["kinds"] = {
            kind_name: _expand_ref(kind_raw, defs, where=f"kinds.{kind_name}", is_kind=True)
            for kind_name, kind_raw in kinds.items()
        }
    return data


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
    main_terminal: tuple[str, ...] = ()
    side_terminal: tuple[str, ...] = ()
    label_en: str | None = None
    parent_triggers: tuple[ParentTriggerSpec, ...] = ()
    child_triggers: tuple[ChildTriggerSpec, ...] = ()

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
    # Definition revision; bumped whenever states/steps/gates change in a way
    # that matters for in-flight items (§17 M7). Distinct from schema version.
    revision: int = 1
    task_types: dict[str, str] = {}
    # Optional English labels keyed by task-type code (§17.115); missing codes
    # fall back to the zh label.
    task_type_labels_en: dict[str, str] = {}
    # Named workflow graphs reusable via ``use`` on kinds/subtypes (§17.119).
    workflow_defs: dict[str, NamedWorkflow] = Field(default_factory=dict)
    kinds: dict[str, KindWorkflow]

    @model_validator(mode="before")
    @classmethod
    def _expand_refs(cls, data: Any) -> Any:
        return _expand_workflow_defs(data)

    @model_validator(mode="after")
    def _validate(self) -> WorkflowSpec:
        if not self.kinds:
            raise ValueError("workflow must define at least one kind")
        unknown_labels = sorted(set(self.task_type_labels_en) - set(self.task_types))
        if unknown_labels:
            raise ValueError(f"task_type_labels_en references unknown task types: {unknown_labels}")
        if "task" in self.kinds:
            subtypes = set(self.kinds["task"].subtypes)
            unknown = sorted(subtypes - set(self.task_types))
            if unknown:
                raise ValueError(f"task subtypes missing from task_types: {unknown}")
        for name, definition in self.workflow_defs.items():
            self._validate_definition(name, definition)
        for kind in self.kinds:
            self.resolve(kind)
            for subtype in self.kinds[kind].subtypes:
                self.resolve(kind, subtype)
        return self

    def _validate_definition(self, name: str, definition: NamedWorkflow) -> None:
        """Check task steps even when a definition is not referenced yet."""
        for src, steps in definition.steps.items():
            for step in steps:
                if step.mode != "task":
                    continue
                assert step.tasks is not None
                if step.tasks.type not in self.task_types:
                    raise ValueError(
                        f"workflow_defs.{name}/{src}/{step.key}: unknown task type "
                        f"{step.tasks.type!r}"
                    )
                child = self.resolve("task", step.tasks.type)
                if step.tasks.complete_on not in child.terminal:
                    raise ValueError(
                        f"workflow_defs.{name}/{src}/{step.key}: complete_on "
                        f"{step.tasks.complete_on!r} is not terminal for task type "
                        f"{step.tasks.type!r}"
                    )

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
        base_main, base_side = classify_terminal(
            base.terminal, base.main_terminal, base.side_terminal
        )
        subtype_key = key[1]
        subtype = base.subtypes.get(subtype_key) if subtype_key is not None else None
        if subtype is None:
            resolved = ResolvedKindWorkflow(
                kind=kind,
                task_type=key[1],
                label=base.label or kind,
                label_en=base.label_en or base.label or kind,
                states=base.states,
                initial=base.initial,
                terminal=base.terminal,
                main_terminal=base_main,
                side_terminal=base_side,
                steps=dict(base.steps),
                gates=dict(base.gates),
                fields=base.fields,
                parent_triggers=base.parent_triggers,
                child_triggers=base.child_triggers,
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
        triggers = (
            subtype.parent_triggers if subtype.parent_triggers is not None else base.parent_triggers
        )
        child_triggers = (
            subtype.child_triggers if subtype.child_triggers is not None else base.child_triggers
        )
        if subtype.states is not None or (
            subtype.main_terminal is not None or subtype.side_terminal is not None
        ):
            subtype_main, subtype_side = classify_terminal(
                tuple(terminal), subtype.main_terminal, subtype.side_terminal
            )
        else:
            subtype_main, subtype_side = base_main, base_side
        resolved = ResolvedKindWorkflow(
            kind=kind,
            task_type=key[1],
            label=subtype.label or base.label or kind,
            label_en=subtype.label_en or base.label_en or subtype.label or base.label or kind,
            states=tuple(states),
            initial=initial,
            terminal=tuple(terminal),
            main_terminal=subtype_main,
            side_terminal=subtype_side,
            steps=steps,
            gates=gates,
            fields=fields,
            parent_triggers=triggers,
            child_triggers=child_triggers,
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
        for index, parent_trigger in enumerate(resolved.parent_triggers):
            where = f"{resolved.kind}: parent_triggers[{index}]"
            if parent_trigger.trigger is not None:
                self._validate_trigger_event(parent_trigger.trigger, f"{where}.trigger")
            if parent_trigger.when is not None:
                self._validate_when(parent_trigger.when, f"{where}.when")
        for index, child_trigger in enumerate(resolved.child_triggers):
            where = f"{resolved.kind}: child_triggers[{index}]"
            if child_trigger.trigger is not None:
                self._validate_trigger_event(child_trigger.trigger, f"{where}.trigger")
            if child_trigger.when is not None:
                self._validate_when(child_trigger.when, f"{where}.when")
            self_to = {child_trigger.self_.to} if child_trigger.self_.to is not None else set()
            unknown_self = sorted((set(child_trigger.self_.from_) | self_to) - state_set)
            if unknown_self:
                raise ValueError(f"{where}: self states {unknown_self} not in states")

    def _validate_trigger_event(self, trigger: TriggerEvent, where: str) -> None:
        unknown_kinds = sorted(set(trigger.kinds) - set(self.kinds))
        if unknown_kinds:
            raise ValueError(f"{where}: unknown child kinds {unknown_kinds}")
        unknown_types = sorted(set(trigger.task_types) - set(self.task_types))
        if unknown_types:
            raise ValueError(f"{where}: unknown task types {unknown_types}")
        if trigger.task_types and trigger.kinds and "task" not in trigger.kinds:
            raise ValueError(f"{where}: tasktypes requires kinds to be empty or include 'task'")

    def _validate_when(self, when: TriggerWhen, where: str) -> None:
        for key in ("any", "all"):
            clause = getattr(when, key)
            if clause is not None:
                self._validate_quantifier(clause, f"{where}.{key}")

    def _validate_quantifier(self, clause: ChildQuantifier, where: str) -> None:
        unknown_kinds = sorted(set(clause.kinds) - set(self.kinds))
        if unknown_kinds:
            raise ValueError(f"{where}: unknown child kinds {unknown_kinds}")
        unknown_types = sorted(set(clause.task_types) - set(self.task_types))
        if unknown_types:
            raise ValueError(f"{where}: unknown task types {unknown_types}")
        if clause.task_types and clause.kinds and "task" not in clause.kinds:
            raise ValueError(f"{where}: tasktypes requires kinds to be empty or include 'task'")
        if clause.and_ is not None:
            self._validate_quantifier(clause.and_, f"{where}.and")
